from flask import Flask, render_template, Response, send_file
from binance.client import Client
from datetime import datetime
import pandas as pd
# from openpyxl import Workbook
import schedule, time, threading, os
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template, request, redirect, url_for


app = Flask(__name__)
# app.config['SQL_ALCHEMY_URL'] = 'sqlite:///database.db'
# app.config['SECRET_KEY'] = 'this'


live_data = []

api_key = 'xQ6ucxBVyApc2fsQ3uGIdn8Rp87YAekx1hzP9W8ZqzWw0orYasOij7RhFVU9NHVE'
api_sec = "API KEY"

client = Client(api_key, api_sec)


# defining a function to fetch the top traders based on trading volume and profit percentage.
def get_top_traders():
    # get the symbol for the trading pair you are interested in (e.g., BTCUSDT).
    symbol = 'BTCUSDT'

    end_time = int(time.time() * 1000)
    start_time = end_time - (3 * 24 * 60 * 60 * 1000)

    # fetching the trading data for the symbol.
    klines = client.futures_klines(symbol=symbol,
                                   interval=Client.KLINE_INTERVAL_1HOUR,
                                   limit=1000,
                                   startTime=start_time,
                                   endTime=end_time)

    # calculating the trading volume, profit percentage, profit gain, buying price, and selling price for each trader.
    trader_data = {}

    for kline in klines:
        timestamp = int(kline[0]) // 1000  # converting milliseconds to seconds.
        trader_id = kline[5]  # the field containing the trader's ID.
        product_traded = symbol
        volume = float(kline[9])  # the field containing trading volume.
        close_price = float(kline[4])  # the field containing the closing price.
        open_price = float(kline[1])  # the field containing the opening price.
        datetime_obj = datetime.fromtimestamp(timestamp)

        if trader_id not in trader_data:
            trader_data[trader_id] = {
                'Trader ID': trader_id,
                'Date': datetime_obj.strftime('%Y-%m-%d'),
                'Time': datetime_obj.strftime('%H:%M:%S'),
                'Product Traded': product_traded,
                'Trading Volume (Second)': 0,
                'Trading Volume (Minute)': 0,
                'Total Earned': 0,
                'Profit Percentage': 0,
                'Profit Gain': 0,
                'Buying Price': 0,
                'Selling Price': 0,
                'last_close_price': close_price

            }

        # Update trading volume for different time intervals.
        current_time = timestamp % 60  # Second
        trader_data[trader_id]['Trading Volume (Second)'] += volume
        if current_time == 0:
            trader_data[trader_id]['Trading Volume (Minute)'] += volume

        current_time = timestamp % 3600  # Hour
        # if current_time == 0:
        # trader_data[trader_id]['Trading Volume (Hour)'] += volume

        # Calculate profit percentage, profit gain, buying price, and selling price.
        # trader_data[trader_id]['Profit Gain'] = round((close_price - open_price), 2)
        trader_data[trader_id]['Buying Price'] = open_price
        trader_data[trader_id]['Selling Price'] = close_price

        profit_gain = ((close_price - open_price) / open_price) * 100
        trader_data[trader_id]['Profit Gain'] += round(profit_gain, 2)
        # trader_data[trader_id]['Total Earned'].append(trader_data[trader_id]['Total Earned'][-1] + profit_gain)

    for trader_id, data in trader_data.items():
        open_price = float(klines[0][1])
        close_price = float(klines[-1][4])
        profit_percentage = ((close_price - open_price) / open_price) * 100
        data['Profit Percentage'] = round(profit_percentage, 2)

    # sort traders by trading volume and profit percentage and get the top 7.
    sorted_traders = sorted(trader_data.values(), key=lambda x: (x['Trading Volume (Second)'], x['Profit Percentage']),
                            reverse=True)[:7]

    return sorted_traders


def fetch_live_data():
    global live_data
    live_data = get_top_traders()


def scheduled_task():
    fetch_live_data()


# Schedule the task to run every 2 minutes.
schedule.every(2).minutes.do(scheduled_task)


# run the scheduled tasks in the background.
def run_scheduled_tasks():
    while True:
        schedule.run_pending()
        time.sleep(1)


scheduler = BackgroundScheduler()


@app.route('/download_in_excel')
def download_in_excel():
    top_traders = get_top_traders()

    df = pd.DataFrame(top_traders)

    excel_file = 'top_traders_report.xlsx'

    df.to_excel(excel_file, index=False)

    return send_file(excel_file, as_attachment=True)


# Function to generate and download individual reports for each trader
def download_excel():
    if not os.path.exists('trader_reports'):
        os.mkdir('trader_reports')

    top_traders_data = get_top_traders()

    for trader in top_traders_data:
        trader_id = trader['Trader ID']
        trader_df = pd.DataFrame([trader])

        # Save the trader's report to a separate Excel file
        filename = f'trader_reports/trader_{trader_id}_report.xlsx'
        trader_df.to_excel(filename, index=False)


scheduler.add_job(download_excel, 'interval', minutes=1440)
scheduler.start()


# Route to trigger the generation and download of trader reports
@app.route('/download_trader_reports')
def download_trader_reports_route():
    download_excel()

    # Return a message indicating that reports have been generated
    return "Trader reports generated successfully."


def determine_trading_action(top_traders_data):
    # defining thresholds for profit percentage and volume.
    buy_profit_threshold = 5.0
    buy_volume_threshold = 10

    sell_profit_threshold = 1.0  # (1%)
    sell_volume_threshold = 5  # 5 USDT

    for trader in top_traders_data:
        profit_percentage = trader['Profit Percentage']
        trading_volume = trader['Trading Volume (Second)']

        # buying condition: High profit and high volume.
        if profit_percentage > buy_profit_threshold and trading_volume > buy_volume_threshold:
            # prompt the user to confirm the buy action
            user_input = input(f"Buy condition met for trader {trader['Trader ID']}. Buy? (y/n): ").strip().lower()
            if user_input == 'y':
                return 'buy'

        # sell condition: Low profit and low volume.
        if profit_percentage < sell_profit_threshold and trading_volume < sell_volume_threshold:
            # prompting the user to confirm the sell action.
            user_input = input(f"Sell condition met for trader {trader['Trader ID']}. Sell? (y/n): ").strip().lower()
            if user_input == 'y':
                return 'sell'

    # if no buy or sell conditions are met, return 'hold' (no action).
    return 'hold'


@app.route('/trade', methods=['POST'])
def trade():
    # fetch data of the top 7 traders using your_module.get_top_traders()
    top_traders_data = get_top_traders()

    # determine the trading action using the determine_trading_action function
    trading_action = determine_trading_action(top_traders_data)

    if trading_action == 'buy':
        # execute a buy action or display a message for buying
        # implement the buy logic or response here
        return "Buy action performed"

    elif trading_action == 'sell':
        # execute a sell action or display a message for selling
        # implement the sell logic or response here
        return "Sell action performed"

    else:
        # handle the case when no action is taken
        return "No action taken"


@app.route('/')
def index():
    top_traders = get_top_traders()
    return render_template('index.html',
                           top_traders=top_traders,
                           live_data=live_data)


if __name__ == '__main__':
    background_thread = threading.Thread(target=run_scheduled_tasks)
    background_thread.start()
    app.run(debug=True)
