# Building the "Publish Leonne's Daily Post" Shortcut

This Shortcut works identically on Mac and iPhone/iPad. It triggers the
server to scrape feeds, generate the edition via the Anthropic API, and
deploy it — all in one tap. It waits for the pipeline to finish and
notifies Leonne when her paper is ready (or if something went wrong).

## Setup on your server FIRST

Before building the Shortcut, deploy these files and restart the service:

```bash
# Copy updated files
scp deploy_server.py your-server:/opt/leonne-deploy/
scp run_pipeline.sh your-server:/opt/leonne-deploy/

# On the server:
sudo chmod +x /opt/leonne-deploy/run_pipeline.sh

# Make sure ANTHROPIC_API_KEY is in the systemd service:
sudo systemctl edit leonne-deploy.service
# Add under [Service]:
#   Environment="ANTHROPIC_API_KEY=sk-ant-your-key-here"

# Also add the /generate route to Caddy:
# In your Caddyfile, the handle block should cover both /deploy and /generate:
#   handle /deploy* {
#       reverse_proxy localhost:8472
#   }
#   handle /generate* {
#       reverse_proxy localhost:8472
#   }

sudo systemctl daemon-reload
sudo systemctl restart leonne-deploy.service
sudo systemctl reload caddy
```

## Build the Shortcut

### Step-by-step (both Mac and iPhone):

1. Open the **Shortcuts** app
2. Tap **+** to create a new shortcut
3. Name it: **Publish Daily Post**
4. Add an icon: 📰 (newspaper) in a warm orange

### Add these actions in order:

---

**Action 1: Text**
- Content: `YOUR_DEPLOY_TOKEN_HERE`
- *(Tap the variable name and rename it to `Token`)*

---

**Action 2: Get Contents of URL**
- URL: `https://leonne.net/generate`
- Method: **POST**
- Headers:
  - Key: `Authorization`
  - Value: `Bearer [Token]`  *(insert the Token variable)*
  - Key: `Content-Type`
  - Value: `application/json`

---

**Action 3: Get Dictionary Value**
- Get value for key: `status`
- From: *Contents of URL*

---

**Action 4: If**
- Input: *Dictionary Value*
- Condition: **is**
- Value: `started`

---

**Action 5 (inside If): Show Notification**
- Title: **Leonne's Daily Post**
- Body: **Generating your paper… ☕**

---

**Action 6 (inside Otherwise): Show Notification**
- Title: **Leonne's Daily Post**
- Body: **Couldn't start generation. The server may be busy or down.**

---

**Action 7 (inside Otherwise): Stop This Shortcut**

---

**Action 8: End If**

---

**Action 9: Wait**
- Duration: **150** seconds

---

**Action 10: Get Contents of URL**
- URL: `https://leonne.net/generate/status`
- Method: **GET**
- Headers:
  - Key: `Authorization`
  - Value: `Bearer [Token]`

---

**Action 11: Get Dictionary Value**
- Get value for key: `last_result`
- From: *Contents of URL*

---

**Action 12: Get Dictionary Value**
- Get value for key: `success`
- From: previous result

---

**Action 13: If**
- Input: *Dictionary Value*
- Condition: **is**
- Value: `true`

---

**Action 14 (inside If): Show Notification**
- Title: **Leonne's Daily Post**
- Body: **Your paper is ready! 📰**

---

**Action 15 (inside Otherwise): Show Notification**
- Title: **Leonne's Daily Post**
- Body: **Something went wrong generating today's edition.**

---

**Action 16: End If**

---

That's it! Six actions to trigger, a wait, then four actions to check
the result and notify. Leonne taps once, puts her phone down, and gets
a notification 2.5 minutes later when her paper is ready.

## Usage

- **Morning routine**: Tap "Publish Daily Post" when Leonne wakes up
- She'll see "Generating your paper… ☕" immediately
- ~2.5 minutes later, she gets "Your paper is ready! 📰"
- Works from Mac, iPhone, iPad — anywhere with internet

## Adding to Home Screen (iPhone)

1. In Shortcuts, long-press the "Publish Daily Post" shortcut
2. Tap **Share** → **Add to Home Screen**
3. Choose the 📰 icon
4. Now it's a one-tap button right on her phone

## Later: Automating it

When Leonne decides she wants it fully automated:
1. Open Shortcuts → **Automation** tab
2. **Create Personal Automation** → **Time of Day**
3. Set to 7:00 AM (or whenever she wants her paper)
4. Action: **Run Shortcut** → select "Publish Daily Post"
5. Turn OFF "Ask Before Running"
6. Done — her paper arrives every morning automatically

Note: When automated, the Shortcut runs in the background. The
notifications still appear on her Lock Screen / Notification Center,
so she'll see "Your paper is ready! 📰" when she picks up her phone.
