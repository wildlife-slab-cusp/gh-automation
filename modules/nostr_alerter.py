name: Keep Render Alive (query params)

on:
  schedule:
    - cron: "*/10 * * * *"
  workflow_dispatch:

jobs:
  ping:
    runs-on: ubuntu-latest
    concurrency:
      group: keep-render-alive
      cancel-in-progress: true

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: 'pip'

      - name: Cache dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-nostr-deps-${{ hashFiles('**/requirements.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-nostr-deps-
            ${{ runner.os }}-pip-

      - name: Install nostr dependencies only
        run: pip install cffi cryptography pycparser secp256k1 websocket-client

      - name: Wake Render service
        id: ping
        run: |
          echo "🚀 Pinging Render at $(date -u)"

          base_url="${{ secrets.RENDER_SERVICE_URL }}"

          agents=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0 Safari/537.36"
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15"
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
          )
          ua=${agents[$RANDOM % ${#agents[@]}]}

          sleep $((RANDOM % 5))

          http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 60 \
               -A "$ua" \
               "$base_url/?Render=data")

          echo "status=$http_code" >> $GITHUB_OUTPUT

      - name: Send Nostr alert if down
        if: steps.ping.outputs.status == '503' || steps.ping.outputs.status == '000'
        env:
          NOSTR_SENDER_PRIVATE_KEY_HEX: ${{ secrets.NOSTR_SENDER_PRIVATE_KEY_HEX }}
          NOSTR_RECEIVER_PUBLIC_KEY_HEX: ${{ secrets.NOSTR_RECEIVER_PUBLIC_KEY_HEX }}
        run: |
          python modules/nostr_alerter.py "🚨 Render returned ${{ steps.ping.outputs.status }} at $(date -u)"