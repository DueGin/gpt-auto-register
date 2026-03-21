"""
ChatGPT auto-register script
支持串行和并发注册模式
"""

import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    TOTAL_ACCOUNTS,
    BATCH_INTERVAL_MIN,
    BATCH_INTERVAL_MAX,
    BATCH_CONCURRENT,
    CREDIT_CARD_INFO
)
from utils import generate_random_password, save_to_txt, update_account_status
from email_service import create_temp_email, wait_for_verification_email
from feishu_bitable import write_account_to_bitable
from browser import (
    create_driver,
    fill_signup_form,
    enter_verification_code,
    fill_profile_info,
    subscribe_plus_trial,
    cancel_subscription
)

# 单个账号注册的最大允许时间
REGISTER_TIMEOUT = 300  # 5 min
# 等待邮箱验证码的最短时间
MIN_VERIFICATION_WAIT_SECONDS = 40


class RegisterTimeoutError(Exception):
    """single register timeout"""
    pass


def register_one_account(monitor_callback=None, account_type: str = "GPT", worker_id: int = 0):
    """
    register one account
    :param monitor_callback: callback func(driver, step_name)
    :param account_type: 账号类型标记
    :param worker_id: 并发 worker 编号（用于日志区分）

    Returns:
        tuple: (email, password, success)
    """
    tag = f"[W{worker_id}]" if worker_id > 0 else ""
    driver = None
    email = None
    password = None
    master_account = None  # 2925 方案下保存主邮箱信息
    bitable_record_id = None
    success = False
    plus_subscribed = False
    register_start_time = time.time()

    def _report(step_name):
        if monitor_callback and driver:
            monitor_callback(driver, step_name)

    def _check_timeout(step_name=""):
        elapsed = time.time() - register_start_time
        if elapsed >= REGISTER_TIMEOUT:
            raise RegisterTimeoutError(
                f"timeout ({int(elapsed)}s, limit {REGISTER_TIMEOUT}s), step: {step_name}"
            )

    def _wait_for_manual_close():
        try:
            while True:
                try:
                    driver.current_url
                    time.sleep(1)
                except:
                    print("detected browser closed, continue...")
                    break
        except KeyboardInterrupt:
            print("\nuser interrupted")
            try:
                driver.quit()
            except:
                pass

    try:
        # 1. create temp email
        print(f"{tag} creating temp email...")
        email, jwt_token = create_temp_email()
        # 2925 方案下 jwt_token 实际是 account dict，保存供后续使用
        if isinstance(jwt_token, dict):
            master_account = jwt_token
            jwt_token = None
        if not email:
            print(f"{tag} create email failed")
            return None, None, False
        _check_timeout("create_email")

        # 2. generate password
        password = generate_random_password()

        # 3. init browser
        driver = create_driver(headless=False)
        _report("init_browser")
        _check_timeout("init_browser")

        # 4. open signup page
        url = "https://chat.openai.com/chat"
        print(f"{tag} opening {url}...")
        driver.get(url)
        time.sleep(3)
        _report("open_page")
        _check_timeout("open_page")

        # 5. fill signup form
        if not fill_signup_form(driver, email, password):
            print(f"{tag} fill signup form failed")
            return email, password, False
        _report("fill_form")
        _check_timeout("fill_form")

        # 6. wait for verification email (use remaining time as timeout)
        time.sleep(5)
        remaining = max(MIN_VERIFICATION_WAIT_SECONDS, int(REGISTER_TIMEOUT - (time.time() - register_start_time)))
        verification_code = wait_for_verification_email(
            jwt_token, timeout=remaining, target_email=email, master_account=master_account
        )

        if not verification_code:
            print(f"{tag} no verification code received")
            return email, password, False
        _check_timeout("wait_verification")

        # 7. enter verification code
        if not enter_verification_code(driver, verification_code):
            print(f"{tag} enter verification code failed")
            return email, password, False
        _report("enter_code")
        _check_timeout("enter_code")

        # 8. fill profile
        if not fill_profile_info(driver):
            print(f"{tag} fill profile failed")
            return email, password, False
        _report("fill_profile")
        _check_timeout("fill_profile")

        # 9. save account info
        save_to_txt(email, password, "registered")
        bitable_ok, bitable_record_id = write_account_to_bitable(
            email,
            password,
            status="registered",
            account_type=account_type,
        )
        if not bitable_ok:
            print(f"{tag} feishu bitable write failed")

        # 10. done
        print(f"\n{tag} " + "=" * 50)
        print(f"{tag} register success!")
        print(f"{tag}    email: {email}")
        print(f"{tag}    password: {password}")
        elapsed = int(time.time() - register_start_time)
        print(f"{tag}    time: {elapsed}s")
        print("=" * 50)

        success = True
        _report("registered")

        def _can_auto_subscribe(card_info):
            required = ("number", "expiry", "cvc")
            missing = [k for k in required if not card_info.get(k)]
            if missing:
                print(f"no card info, skip auto subscribe: {', '.join(missing)}")
                return False
            return True

        if _can_auto_subscribe(CREDIT_CARD_INFO):
            _check_timeout("pre_plus")
            print("waiting for page stable...")
            time.sleep(5)

            # 11. subscribe plus trial
            print("\n" + "-" * 30)
            print("start plus trial")
            print("-" * 30)

            if subscribe_plus_trial(driver):
                plus_subscribed = True
                print("plus trial success!")
                update_account_status(email, "plus_subscribed", record_id=bitable_record_id)
                _report("plus_subscribed")
                _check_timeout("plus_subscribed")

                # 12. cancel subscription
                print("\n" + "-" * 30)
                print("cancelling subscription...")
                print("-" * 30)

                time.sleep(5)
                if cancel_subscription(driver):
                    print("subscription cancelled!")
                    update_account_status(email, "cancelled")
                    _report("subscription_cancelled")
                else:
                    print("cancel subscription failed, please cancel manually!")
                    update_account_status(email, "cancel_failed")
                    _report("cancel_failed")
            else:
                print("plus trial failed")
                update_account_status(email, "plus_failed")
                _report("plus_failed")

        success = True
        if plus_subscribed:
            time.sleep(5)

    except RegisterTimeoutError as e:
        elapsed = int(time.time() - register_start_time)
        print(f"\ntimeout ({elapsed}s), skip this account: {e}")
        if email:
            update_account_status(email, f"timeout({elapsed}s)")
        return email, password, False

    except InterruptedError:
        print("user interrupted")
        if email:
            update_account_status(email, "interrupted")
        return email, password, False

    except Exception as e:
        print(f"error: {e}")
        if email and password:
            update_account_status(email, f"error: {str(e)[:50]}")

    finally:
        if driver:
            if plus_subscribed:
                print("\n" + "=" * 50)
                print("register done")
                print("please check browser, close window to continue")
                print("=" * 50)
                _wait_for_manual_close()
            elif success:
                print("\n" + "=" * 50)
                print("register done (no plus), closing browser")
                print("=" * 50)
                try:
                    driver.quit()
                except:
                    pass
            else:
                # timeout or failed, close browser directly
                print("closing browser, preparing next register...")
                try:
                    driver.quit()
                except:
                    pass

    return email, password, success


def _run_one_task(task_id, total, worker_id):
    """并发注册的单个任务（在线程池中运行）"""
    print(f"\n[W{worker_id}] " + "#" * 50)
    print(f"[W{worker_id}] registering task {task_id}/{total}")
    print(f"[W{worker_id}] " + "#" * 50 + "\n")

    email, password, success = register_one_account(worker_id=worker_id)
    return task_id, email, password, success


def run_batch():
    """
    batch register accounts
    支持并发模式：concurrent > 1 时使用线程池同时开多个浏览器
    """
    concurrent = max(1, BATCH_CONCURRENT)

    print("\n" + "=" * 60)
    print(f"start batch register, target: {TOTAL_ACCOUNTS}, concurrent: {concurrent}")
    print("=" * 60 + "\n")

    time.sleep(2)

    success_count = 0
    fail_count = 0
    registered_accounts = []

    if concurrent <= 1:
        # ========== 串行模式（原逻辑） ==========
        for i in range(TOTAL_ACCOUNTS):
            print("\n" + "#" * 60)
            print(f"registering {i + 1}/{TOTAL_ACCOUNTS}")
            print("#" * 60 + "\n")

            email, password, success = register_one_account()

            if success:
                success_count += 1
                registered_accounts.append((email, password))
            else:
                fail_count += 1

            # show progress
            print("\n" + "-" * 40)
            print(f"progress: {i + 1}/{TOTAL_ACCOUNTS}")
            print(f"   success: {success_count}")
            print(f"   failed: {fail_count}")
            print("-" * 40)

            # wait before next register
            if i < TOTAL_ACCOUNTS - 1:
                wait_time = random.randint(BATCH_INTERVAL_MIN, BATCH_INTERVAL_MAX)
                print(f"\nwaiting {wait_time}s before next register...")
                time.sleep(wait_time)

    else:
        # ========== 并发模式 ==========
        print(f"🚀 并发模式启动，同时运行 {concurrent} 个浏览器\n")
        completed = 0

        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            futures = {}
            for i in range(TOTAL_ACCOUNTS):
                worker_id = (i % concurrent) + 1
                future = executor.submit(_run_one_task, i + 1, TOTAL_ACCOUNTS, worker_id)
                futures[future] = i + 1

                # 每提交 concurrent 个任务后，等一小段间隔再提交下一批
                # 避免同时启动太多浏览器
                if (i + 1) % concurrent == 0 and (i + 1) < TOTAL_ACCOUNTS:
                    # 等待当前这一批完成
                    for done_future in as_completed(list(futures.keys())[:concurrent]):
                        task_id, email, password, success = done_future.result()
                        completed += 1
                        if success:
                            success_count += 1
                            registered_accounts.append((email, password))
                        else:
                            fail_count += 1

                        print(f"\n📊 progress: {completed}/{TOTAL_ACCOUNTS} | success: {success_count} | failed: {fail_count}")
                        del futures[done_future]

                    # 批次间等待
                    wait_time = random.randint(BATCH_INTERVAL_MIN, BATCH_INTERVAL_MAX)
                    print(f"\n⏳ 批次间等待 {wait_time}s...")
                    time.sleep(wait_time)

            # 等待剩余的任务完成
            for done_future in as_completed(futures):
                task_id, email, password, success = done_future.result()
                completed += 1
                if success:
                    success_count += 1
                    registered_accounts.append((email, password))
                else:
                    fail_count += 1

                print(f"\n📊 progress: {completed}/{TOTAL_ACCOUNTS} | success: {success_count} | failed: {fail_count}")

    # final stats
    print("\n" + "=" * 60)
    print("batch register done")
    print("=" * 60)
    print(f"   total: {TOTAL_ACCOUNTS}")
    print(f"   success: {success_count}")
    print(f"   failed: {fail_count}")

    if registered_accounts:
        print("\nregistered accounts:")
        for email, password in registered_accounts:
            print(f"   - {email}")

    print("=" * 60)


if __name__ == "__main__":
    run_batch()
