// ---- horae (Homepage): mount the suite masthead outside the React root ----
(function () {
  function mount() {
    if (document.getElementById("masthead")) return;
    var m = document.createElement("div"); m.id = "masthead"; m.className = "wrap"; m.style.paddingBottom = "0";
    document.body.insertBefore(m, document.body.firstChild);
    Suite.mount({ app: "horae" });
    Suite.setLive(true, "Online");
    Suite.Oracle.register(function () {
      return Array.prototype.map.call(document.querySelectorAll(".service-card"), function (c) {
        var a = c.closest("a") || c.querySelector("a"), el = c.querySelector(".service-name"), n = el && el.firstChild ? el.firstChild.textContent.trim() : "";
        return { group: "On horae", icon: n.charAt(0) || "•", title: "Open " + n, sub: (c.querySelector(".service-description") || {}).textContent || "",
                 run: function () { if (a) window.open(a.href, "_blank", "noopener"); } };
      });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
})();
