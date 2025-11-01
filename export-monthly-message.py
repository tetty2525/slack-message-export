import requests
import json
import csv
import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs

# .envファイルを読み込む
load_dotenv()

# ---- 1. 設定 ----
# 環境変数からトークンとユーザーIDを読み込む
SLACK_TOKEN = os.getenv("SLACK_TOKEN")
USER_ID = os.getenv("SLACK_USER_ID")

# 環境変数が設定されているか確認
if not SLACK_TOKEN:
    raise ValueError("環境変数 SLACK_TOKEN が設定されていません")
if not USER_ID:
    raise ValueError("環境変数 SLACK_USER_ID が設定されていません")

headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}

# ---- 2. 検索クエリの作成 (過去30日分) ----
date_30_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
search_query = f"from:@{USER_ID} after:{date_30_days_ago}"

print(f"実行クエリ: {search_query}")

# ---- 3. 親メッセージを取得する関数を定義 ----
def get_parent_message(channel_id, thread_ts):
    """
    conversations.replies APIを使って親メッセージを取得する
    """
    try:
        # レートリミット対策で1秒待機
        time.sleep(1) 
        
        params = {
            "channel": channel_id,
            "ts": thread_ts,      # スレッドのタイムスタンプ（親のts）
            "limit": 1            # 親メッセージ1件だけ取得
        }
        response = requests.get("https://slack.com/api/conversations.replies", headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("ok") and data.get("messages"):
            parent_msg = data["messages"][0]
            # 親メッセージの投稿者を特定（userキーかusernameキー）
            parent_user = parent_msg.get("user") or parent_msg.get("username", "N/A")
            return parent_msg.get("text", ""), parent_user
        else:
            print(f"  [Warn] 親メッセージ取得失敗 (ts:{thread_ts}): {data.get('error')}")
            return "Error: Not Found", "N/A"
            
    except requests.exceptions.RequestException as e:
        print(f"  [Error] 親メッセージAPIリクエストエラー: {e}")
        return "Error: Request Failed", "N/A"

# ---- 4. メインのAPI実行 (search.messages) ----
search_params = {
    "query": search_query,
    "count": 100,
    "sort": "timestamp",
    "sort_dir": "desc"
}

try:
    response = requests.get("https://slack.com/api/search.messages", headers=headers, params=search_params)
    response.raise_for_status() 
    
    data = response.json()

    if data.get("ok"):
        print("APIリクエスト成功！")
        
        messages = data.get("messages", {}).get("matches", [])
        
        if not messages:
            print("メッセージが見つかりませんでした。")
            exit()

        print(f"合計 {len(messages)} 件のメッセージ（のべ）が見つかりました。親メッセージの取得を開始します...")
        
        # デバッグ: 最初のメッセージの構造を確認
        if messages:
            print("\n[デバッグ] 最初のメッセージの構造:")
            first_msg = messages[0]
            print(f"  Keys: {list(first_msg.keys())}")
            print(f"  ts: {first_msg.get('ts')}")
            print(f"  thread_ts: {first_msg.get('thread_ts')}")
            print(f"  permalink: {first_msg.get('permalink')}\n")

        # ---- 5. CSVへの書き出し (親メッセージ情報) ----
        output_filename = "slack_export_with_replies.csv"
        with open(output_filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            # ヘッダーを拡張
            writer.writerow([
                "Timestamp", "User", "Channel", "Message Text", "Permalink",
                "Parent Message Text", "Parent Message User"
            ])
            
            for msg in messages:
                ts = datetime.fromtimestamp(float(msg.get("ts", 0)))
                
                parent_text = ""
                parent_user = ""
                
                # Permalinkから thread_ts を抽出
                permalink = msg.get("permalink", "")
                thread_ts_from_url = None
                if "thread_ts=" in permalink:
                    parsed_url = urlparse(permalink)
                    query_params = parse_qs(parsed_url.query)
                    if "thread_ts" in query_params:
                        thread_ts_from_url = query_params["thread_ts"][0]
                
                # これが「返信」の場合 (thread_ts が存在し、tsと異なる)
                msg_ts = str(msg.get("ts", ""))
                if thread_ts_from_url and msg_ts != thread_ts_from_url:
                    print(f"  -> 返信を発見 (ts:{msg_ts}, thread_ts:{thread_ts_from_url})。親メッセージを取得します...")
                    parent_text, parent_user = get_parent_message(msg["channel"]["id"], thread_ts_from_url)

                writer.writerow([
                    ts.strftime('%Y-%m-%d %H:%M:%S'),
                    msg.get("username", "N/A"),
                    msg.get("channel", {}).get("name", "N/A"),
                    msg.get("text", ""),
                    msg.get("permalink", ""),
                    parent_text,
                    parent_user
                ])
                
        print(f"\n'{output_filename}' に書き出しました。")

    else:
        print(f"APIエラー: {data.get('error')}")

except requests.exceptions.RequestException as e:
    print(f"HTTPリクエストエラー: {e}")