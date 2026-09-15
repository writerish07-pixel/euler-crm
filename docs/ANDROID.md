# Install Euler CRM on Android (first)

The website stays live. This puts the same CRM on a phone as an app named **Euler CRM**.

Package: `com.eulermotors.crm`  
API: `https://euler-crm-production.up.railway.app` (same as the website)

## Download (zip)

Use this **direct download** (opens the zip, not a GitHub preview page):

https://raw.githubusercontent.com/writerish07-pixel/euler-crm/cursor/native-android-ios-996c/files/euler_crm_android.zip

If that still fails, open this page and tap **Download**:

https://github.com/writerish07-pixel/euler-crm/blob/cursor/native-android-ios-996c/files/euler_crm_android.zip

Inside the zip:

- `Euler-CRM.apk` — the app
- `INSTALL.txt` — these same steps

## Install on a phone

1. Unzip `euler_crm_android.zip`.
2. Copy `Euler-CRM.apk` to the phone (WhatsApp, Drive, USB, or Downloads).
3. On the phone: **Settings → Security** (or **Apps**) → allow **Install unknown apps** for Chrome / Files / WhatsApp.
4. Open `Euler-CRM.apk` → **Install**.
5. Open **Euler CRM** and sign in with the same user ID and password as the website.

If Android says “Play Protect”, choose **Install anyway** for this dealer-internal app.

Uninstall anytime: long-press the icon → Uninstall. The website is not affected.

## Rebuild later (when the CRM UI changes)

Website deploys do **not** update the installed app. On a computer with Node and Android Studio:

```bash
cd frontend
yarn
yarn cap:sync
npx cap open android
```

In Android Studio: **Run** on a USB phone, or **Build → Build Bundle(s) / APK(s) → Build APK(s)**.

Play Store needs a **signed release** (keystore + Play Console). Say when you want that; Android testing does not need it.
