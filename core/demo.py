"""動作確認用デモデータの共通定数 (seed_demo_users / seed_analytics で共有)。

※ accounts/migrations/0003 は、あとからコードを変えても動きが変わらないよう同じ値を直接書いている。
  ここを変えるときは、新しいマイグレーションで既存データのグループ名も移すこと。
"""

DEMO_USER_GROUP = "デモ利用者"
DEMO_MANAGER_GROUP = "デモ管理者"
DEMO_DOMAIN = "demo.mikke.test"  # 予約済みのテスト用ドメイン (実在しない)
