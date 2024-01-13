import requests
import time


def main():
    while True:
        url = "http://127.0.0.1:8000/update_tasks"
        r = requests.get(url)

        updated = False

        if r.status_code != 200:
            print(f"Failed to send update request: {r.status_code} {r.text}")
        else:
            print(f"<{r.status_code}>", end="")
            for task_updated in r.json():
                updated = updated or (task_updated["task_name"] == 'esi.market_orders' and task_updated["successful"])
                print(f"\n{task_updated}")

        if updated:
            url = "http://127.0.0.1:8000/test?rep_yield=0.55&tax=0.036&roi=0.1"
            r = requests.get(url)

        time.sleep(1)


if __name__ == "__main__":
    main()
