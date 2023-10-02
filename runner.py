import requests
import time

def main():
    while True:
        print("Sending update request.")
        url = 'http://127.0.0.1:8000/update'
        r = requests.get(url)
        print(f"Task Status's: {r.json()}")
        time.sleep(5)
        
if __name__ == '__main__':
    main()