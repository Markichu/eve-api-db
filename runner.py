import requests
import datetime
import time
import winsound

def main():
    while True:
        print(f"Updating Orders at {datetime.datetime.utcnow()}")
        url = 'http://127.0.0.1:8000/update'
        r = requests.get(url)
        if r.status_code == 200:
            expires = r.json()['expires']
            time_to_complete = datetime.datetime.strptime(expires, '%a, %d %b %Y %H:%M:%S %Z') - datetime.datetime.utcnow()
        else:
            print(f"Error: {r.json()['message']}, {r.json()['status_code']}, {r.json()['reason']}")
            time_to_complete = datetime.timedelta(minutes=1)
        print(f"Updated Orders at {datetime.datetime.utcnow()}, next update at {datetime.datetime.utcnow() + time_to_complete}")
        url = 'http://127.0.0.1:8000/reprocess'
        r = requests.get(url)
        if r.json():
            winsound.Beep(440, 500)
        for _, value in r.json():
            print(value["name"])
            print(f"x {value['portion_size']:<5} @ {value['unit_price']:.2f} {value['profit']:10.2f} {value['roi']:8.4f} {value['buy_price']:10.2f}->{value['sell_price']:.2f}")
        time.sleep(max(time_to_complete.total_seconds(), 0))
        
if __name__ == '__main__':
    main()