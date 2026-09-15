# Euler CRM Android and iOS apps

The live website stays on Render / Cloudflare. These store apps wrap the **same** React CRM and talk to the **same** Railway API (`https://euler-crm-production.up.railway.app`). Staff keep using the browser until you publish the apps and tell them to switch.

## One-time setup

On a machine with Node 20+:

```bash
cd frontend
yarn
yarn build
npx cap sync
```

### Android (Windows / Mac / Linux)

1. Install [Android Studio](https://developer.android.com/studio) (SDK 35, build-tools, a device or emulator).
2. `cd frontend && npx cap open android`
3. Run on a phone/emulator, or **Build → Generate Signed Bundle / APK** for Play Console.

Package id: `com.eulermotors.crm`

### iOS (Mac only)

1. Install Xcode 16+.
2. `cd frontend && npx cap sync ios && npx cap open ios`
3. Sign with an Apple Developer team, then Archive for TestFlight / App Store.

Bundle id: `com.eulermotors.crm`

## After a CRM UI change

Web deploys as today. For the store apps:

```bash
cd frontend
yarn build
npx cap sync
```

Then rebuild in Android Studio / Xcode. A website deploy does **not** update phones that already installed the app.

## What does not change

- Browser PWA / “Add to Home Screen”
- Railway API, Google Sheets, login, roles
- Cloudflare / Render frontend hosting
