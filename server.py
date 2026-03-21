import logging
import threading
import time
import queue
import builtins
import os
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, request, send_from_directory

# 导入业务逻辑
import main
import browser
import email_service
import feishu_bitable
from config import cfg

app = Flask(__name__, static_url_path='')

# ==========================================
# 🔧 状态管理与日志捕获
# ==========================================

# ==========================================
# 🔧 状态管理与日志捕获
# ==========================================

# 全局状态
class AppState:
    def __init__(self):
        self.is_running = False
        self.stop_requested = False
        self.success_count = 0
        self.fail_count = 0
        self.current_action = "等待启动"
        self.logs = []
        self.lock = threading.Lock()
        
        # MJPEG 流缓冲区
        self.last_frame = None 
        self.frame_lock = threading.Lock()

    def add_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.logs.append(f"[{timestamp}] {message}")
            if len(self.logs) > 1000:
                self.logs.pop(0)

    def get_logs(self, start_index=0):
        with self.lock:
            return list(self.logs[start_index:])
            
    def update_frame(self, frame_bytes):
        with self.frame_lock:
            self.last_frame = frame_bytes
            
    def get_frame(self):
        with self.frame_lock:
            return self.last_frame

state = AppState()

# Hack: 劫持 print 函数以捕获日志
original_print = builtins.print
def hooked_print(*args, **kwargs):
    sep = kwargs.get('sep', ' ')
    msg = sep.join(map(str, args))
    state.add_log(msg)
    original_print(*args, **kwargs)

# 应用劫持
main.print = hooked_print
browser.print = hooked_print
email_service.print = hooked_print
feishu_bitable.print = hooked_print

# ==========================================
# 🧵 后台工作线程
# ==========================================

def _register_one_with_monitor(task_id, total, worker_id):
    """
    并发注册单个账号（带截图监控回调）
    在线程池中运行，线程安全
    """
    def monitor(driver, step):
        # 1. 检查是否请求停止
        if state.stop_requested:
            main.print(f"[W{worker_id}] 🛑 检测到停止请求，正在中断任务...")
            raise InterruptedError("用户请求停止")

        # 2. 截图更新流 (MJPEG) — 多个 worker 共用一个帧缓冲，最新截的覆盖
        try:
            png_bytes = driver.get_screenshot_as_png()
            state.update_frame(png_bytes)
        except Exception as e:
            main.print(f"[W{worker_id}] ⚠️ 截图流更新失败: {e}")

    try:
        email, password, success = main.register_one_account(
            monitor_callback=monitor, worker_id=worker_id
        )
        return task_id, email, password, success
    except InterruptedError:
        main.print(f"[W{worker_id}] 🛑 任务已中断")
        return task_id, None, None, False
    except Exception as e:
        main.print(f"[W{worker_id}] ❌ 异常: {str(e)}")
        return task_id, None, None, False


def worker_thread(count):
    concurrent = max(1, cfg.batch.concurrent)
    state.is_running = True
    state.stop_requested = False
    state.success_count = 0
    state.fail_count = 0
    state.current_action = f"🚀 任务启动，目标: {count}，并发: {concurrent}"

    # 清空上一轮的画面，避免显示残留
    state.update_frame(None)

    main.print(f"🚀 开始批量任务，计划注册: {count} 个，并发: {concurrent}")

    try:
        if concurrent <= 1:
            # ========== 串行模式 ==========
            for i in range(count):
                if state.stop_requested:
                    main.print("🛑 用户停止了任务")
                    break

                state.current_action = f"正在注册 ({i+1}/{count})..."
                _, _, _, success = _register_one_with_monitor(i + 1, count, 0)

                if success:
                    state.success_count += 1
                else:
                    state.fail_count += 1

                # 间隔等待
                if i < count - 1 and not state.stop_requested:
                    wait_time = random.randint(cfg.batch.interval_min, cfg.batch.interval_max)
                    main.print(f"⏳ 冷却中，等待 {wait_time} 秒...")
                    for _ in range(wait_time):
                        if state.stop_requested: break
                        time.sleep(1)
        else:
            # ========== 并发模式 ==========
            main.print(f"🚀 并发模式，同时运行 {concurrent} 个浏览器")
            completed = 0
            task_index = 0

            while task_index < count and not state.stop_requested:
                # 本批次要提交的任务数
                batch_size = min(concurrent, count - task_index)
                state.current_action = f"并发注册中 ({task_index+1}-{task_index+batch_size}/{count})..."

                with ThreadPoolExecutor(max_workers=batch_size) as executor:
                    futures = {}
                    for j in range(batch_size):
                        if state.stop_requested:
                            break
                        worker_id = j + 1
                        task_id = task_index + j + 1
                        future = executor.submit(
                            _register_one_with_monitor, task_id, count, worker_id
                        )
                        futures[future] = task_id

                    # 等待本批次全部完成
                    for done_future in as_completed(futures):
                        try:
                            _, email, password, success = done_future.result()
                            completed += 1
                            if success:
                                state.success_count += 1
                            else:
                                state.fail_count += 1
                        except Exception as e:
                            completed += 1
                            state.fail_count += 1
                            main.print(f"❌ worker 异常: {e}")

                        main.print(
                            f"📊 进度: {completed}/{count} | "
                            f"成功: {state.success_count} | 失败: {state.fail_count}"
                        )

                task_index += batch_size

                # 批次间等待
                if task_index < count and not state.stop_requested:
                    wait_time = random.randint(cfg.batch.interval_min, cfg.batch.interval_max)
                    state.current_action = f"批次冷却中，等待 {wait_time} 秒..."
                    main.print(f"⏳ 批次冷却中，等待 {wait_time} 秒...")
                    for _ in range(wait_time):
                        if state.stop_requested: break
                        time.sleep(1)

    except Exception as e:
        main.print(f"💥 严重错误: {e}")
    finally:
        state.is_running = False
        state.current_action = f"任务已完成 (成功: {state.success_count}, 失败: {state.fail_count})"
        main.print("🏁 任务结束")

# ==========================================
# 🌊 MJPEG 流生成器
# ==========================================
def gen_frames():
    """生成流数据的生成器"""
    while True:
        frame = state.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/png\r\n\r\n' + frame + b'\r\n')
        else:
            # 如果没有画面（例如刚启动），可以发送一个空帧或者只是等待
            pass
            
        time.sleep(0.5) # 控制刷新率，避免浏览器过于频繁请求

@app.route('/video_feed')
def video_feed():
    return Flask.response_class(gen_frames(),
                               mimetype='multipart/x-mixed-replace; boundary=frame')

# ==========================================
# 🌐 API 接口
# ==========================================

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/status')
def get_status():
    # 获取库存数
    total_inventory = 0
    if os.path.exists(cfg.files.accounts_file):
        try:
            with open(cfg.files.accounts_file, 'r', encoding='utf-8') as f:
                total_inventory = sum(1 for line in f if '@' in line)
        except:
            pass

    return jsonify({
        "is_running": state.is_running,
        "current_action": state.current_action,
        "success": state.success_count,
        "fail": state.fail_count,
        "total_inventory": total_inventory,
        "logs": state.get_logs(int(request.args.get('log_index', 0)))
    })

@app.route('/api/start', methods=['POST'])
def start_task():
    if state.is_running:
        return jsonify({"error": "Already running"}), 400
    
    data = request.json
    count = data.get('count', 1)
    
    threading.Thread(target=worker_thread, args=(count,), daemon=True).start()
    return jsonify({"status": "started"})

@app.route('/api/stop', methods=['POST'])
def stop_task():
    if not state.is_running:
        return jsonify({"error": "Not running"}), 400
    
    state.stop_requested = True
    return jsonify({"status": "stopping"})

@app.route('/api/accounts')
def get_accounts():
    accounts = []
    if os.path.exists(cfg.files.accounts_file):
        try:
            with open(cfg.files.accounts_file, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split('|')
                    if len(parts) >= 2:
                        accounts.append({
                            "email": parts[0].strip(),
                            "password": parts[1].strip(),
                            "status": parts[2].strip() if len(parts) > 2 else "",
                            "time": parts[3].strip() if len(parts) > 3 else ""
                        })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    # 反转列表，最新的在前
    return jsonify(accounts[::-1])

if __name__ == '__main__':
    from waitress import serve
    print("🌐 Web Server started at http://localhost:7070")
    # 使用生产级服务器 Waitress
    # threads=6 支持并发：前端页面 + API轮询 + MJPEG流 + 后台任务
    serve(app, host='0.0.0.0', port=7070, threads=6)
