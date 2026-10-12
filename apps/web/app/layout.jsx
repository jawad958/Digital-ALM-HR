import "./globals.css";

export const metadata = {
  title: { default: "Alpago HR", template: "%s · Alpago HR" },
  description: "Alpago HR Platform — hiring, approvals, and the full employee lifecycle.",
  robots: { index: false, follow: false },
};

// Pre-paint theme to avoid flash of wrong theme on first paint
const themeInit = `(function(){try{var t=localStorage.getItem('alpago-theme');if(!t){t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}document.documentElement.setAttribute('data-theme',t);}catch(e){}})();`;

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
