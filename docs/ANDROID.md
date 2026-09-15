# Install Euler CRM on Android (first)

The website stays live. This puts the same CRM on a phone as an app named **Euler CRM**.

Package: `com.eulermotors.crm`  
API: `https://euler-crm-production.up.railway.app` (same as the website)

## Fastest: install the debug APK on a phone

A debug APK is for you and staff to try. It is **not** the Play Store build.

1. Copy `euler_crm_android_debug.apk` to the phone (WhatsApp, Drive, USB, or Downloads).
2. On the phone: **Settings → Security** (or **Apps**) → allow **Install unknown apps** for Chrome / Files / WhatsApp.
3. Open the APK → **Install**.
4. Open **Euler CRM** and sign in with the same user ID and password as the website.

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
