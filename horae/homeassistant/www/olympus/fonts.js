// Olympus theme: load the suite's fonts (Inter, JetBrains Mono) into Home Assistant's page.
// Loaded through `frontend: extra_module_url` (see horae/scripts/ha-theme.sh). Fonts declared on the page work inside
// HA's shadow DOM too. Without this file the Olympus theme falls back to the system font, which is fine.
const href = "https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400..700&family=JetBrains+Mono:wght@400;500&display=swap";
if (!document.querySelector(`link[href="${href}"]`)) {
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}
