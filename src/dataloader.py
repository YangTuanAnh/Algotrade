import psycopg
import argparse
import os
import pandas as pd
import time
from dotenv import load_dotenv
from .constants import RATE_LIMIT_SECONDS, FETCH_ROWS, DAILY_QUERY, VNINDEX_OPEN_CLOSE

load_dotenv()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--from_date", help="-f '2025-01-01'")
    parser.add_argument("-t", "--to_date", help="-t '2025-12-31'")
    parser.add_argument("-o", "--output_path", help="-o data/train.csv")
    parser.add_argument("-vni", "--get_vnindex", action="store_true")
    args = parser.parse_args()

    conn = psycopg.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )

    time_window = (args.from_date, args.to_date)
    result = []
    with conn.cursor() as cur:
        if args.get_vnindex:
            cur.execute(VNINDEX_OPEN_CLOSE, time_window)
        else:
            cur.execute(DAILY_QUERY, time_window)
        curr = []
        while True:
            curr = cur.fetchmany(FETCH_ROWS)
            if len(curr) == 0:
                break
            result.extend(curr)
            print(f"Current number of tick: {len(result)}")
            time.sleep(RATE_LIMIT_SECONDS)

    print(f"Total number of tick: {len(result)}")

    print("The first five ticks are: ")
    print(result[:5])

    if args.get_vnindex:
        df = pd.DataFrame(result, columns=["datetime", "open", "close"])
    else:
        df = pd.DataFrame(result, columns=["datetime", "open", "close", "high", "low"])
    df = df.set_index("datetime")
    df.to_csv(args.output_path)
    print("Saved tick data for", time_window, "at", args.output_path)
