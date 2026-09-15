/** Capacitor bootstrap. Safe on the live website: plugins no-op in a browser. */

export async function bootNativeShell() {
  if (typeof window === "undefined") return false;
  try {
    const { Capacitor } = await import("@capacitor/core");
    if (!Capacitor.isNativePlatform()) return false;
    document.documentElement.classList.add("euler-native");
    const [
      { StatusBar, Style },
      { Keyboard, KeyboardResize },
      { SplashScreen },
      { App },
    ] = await Promise.all([
      import("@capacitor/status-bar"),
      import("@capacitor/keyboard"),
      import("@capacitor/splash-screen"),
      import("@capacitor/app"),
    ]);
    await StatusBar.setOverlaysWebView({ overlay: false }).catch(() => undefined);
    await StatusBar.setBackgroundColor({ color: "#ffffff" }).catch(() => undefined);
    await StatusBar.setStyle({ style: Style.Light }).catch(() => undefined);
    try {
      await Keyboard.setResizeMode({ mode: KeyboardResize.Body });
    } catch { /* Keyboard plugin optional on web preview */ }
    await SplashScreen.hide().catch(() => undefined);
    App.addListener("backButton", ({ canGoBack }) => {
      if (canGoBack) {
        window.history.back();
        return;
      }
      App.exitApp();
    });
    return true;
  } catch {
    return false;
  }
}
