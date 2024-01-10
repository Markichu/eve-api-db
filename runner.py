import requests
import time


def main():
    while True:
        url = "http://127.0.0.1:8000/update_tasks"
        r = requests.get(url)

        updated = False

        if r.status_code != 200:
            print(f"Failed to send update request: {r.status_code}")
        else:
            print(f"Update request sent successfully: {r.status_code}")
            for task_updated in r.json():
                updated = updated or task_updated["successful"]
                print(task_updated)

        if updated:
            url = "http://127.0.0.1:8000/test?rep_yield=0.55&tax=0.036&roi=0.1"
            r = requests.get(url)

        time.sleep(5)


if __name__ == "__main__":
    main()
