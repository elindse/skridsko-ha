/* Skridsko isobservasjoner – dashbordkort (custom:skridsko-card)
 *
 * type: custom:skridsko-card
 * entity: sensor.skridsko_isobservasjoner_siste_observasjon   (valgfri – finnes automatisk)
 * image: image.skridsko_isobservasjoner_siste_bilde           (valgfri)
 * history: 3                                                  (antall tidligere, valgfri)
 */
class SkridskoCard extends HTMLElement {
  setConfig(config) {
    this._config = { history: 3, ...config };
  }

  static getStubConfig() {
    return { history: 3 };
  }

  getCardSize() {
    return 6;
  }

  _find(prefix, suffixes) {
    const ids = Object.keys(this._hass.states).filter((id) => id.startsWith(prefix) && id.includes("skridsko"));
    return ids.find((id) => suffixes.some((s) => id.endsWith(s))) || null;
  }

  set hass(hass) {
    this._hass = hass;
    const sensorId = this._config.entity || this._find("sensor.", ["siste_observasjon", "last_observation"]);
    const imageId = this._config.image || this._find("image.", ["siste_bilde", "last_image"]);
    const s = sensorId && hass.states[sensorId];
    const img = imageId && hass.states[imageId];
    const key = JSON.stringify([s && s.last_updated, img && img.attributes.entity_picture]);
    if (key === this._last) return;
    this._last = key;
    this._render(s, img);
  }

  _esc(t) {
    return String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  _when(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    const now = new Date();
    const time = d.toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit" });
    if (d.toDateString() === now.toDateString()) return `i dag ${time}`;
    return d.toLocaleDateString("nb-NO", { day: "numeric", month: "short" });
  }

  _render(s, img) {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    if (!s || s.state === "unknown" || s.state === "unavailable") {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px;color:var(--secondary-text-color)">Ingen isobservasjoner ennå.</div></ha-card>`;
      return;
    }
    const a = s.attributes;
    const pic = img && img.state !== "unavailable" ? img.attributes.entity_picture : null;
    const n = (a.images || []).length;
    const hist = (a.history || []).slice(0, this._config.history);
    const chip = (text, bg, fg) => `<span class="chip" style="background:${bg};color:${fg}">${this._esc(text)}</span>`;
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { overflow: hidden; }
        .pic { height: 210px; background: var(--secondary-background-color) center/cover no-repeat; position: relative; display:block; }
        .count { position:absolute; right:10px; bottom:10px; font-size:12px; color:#fff; background:#00000099; padding:4px 10px; border-radius:12px; }
        .body { padding: 16px; display:flex; flex-direction:column; gap:10px; }
        .head { display:flex; align-items:baseline; justify-content:space-between; gap:8px; }
        h2 { margin:0; font-size:20px; font-weight:500; }
        .muted { font-size:13px; color: var(--secondary-text-color); }
        .chips { display:flex; flex-wrap:wrap; gap:6px; }
        .chip { font-size:13px; padding:4px 10px; border-radius:12px; }
        p { margin:0; font-size:14px; line-height:1.5; white-space:pre-line; }
        a.open { font-size:14px; font-weight:500; color: var(--primary-color); text-decoration:none; }
        .hist { border-top:1px solid var(--divider-color); padding:8px 16px 12px; }
        .row { display:flex; align-items:center; gap:10px; padding:6px 0; color: var(--primary-text-color); text-decoration:none; }
        .dot { width:10px; height:10px; border-radius:5px; flex-shrink:0; }
        .row span.name { flex-grow:1; font-size:14px; }
      </style>
      <ha-card>
        ${pic ? `<a class="pic" href="${this._esc(a.url)}" target="_blank" rel="noopener" style="background-image:url('${pic}')" aria-label="Åpne observasjonen">${n > 1 ? `<span class="count">${n} bilder</span>` : ""}</a>` : ""}
        <div class="body">
          <div class="head"><h2>${this._esc(s.state)}</h2><span class="muted">${this._esc(this._when(a.received))}</span></div>
          <div class="chips">
            ${chip(a.short_status, a.color || "#757575", "#fff")}
            ${a.isinfo ? chip(a.isinfo, "var(--secondary-background-color)", "var(--primary-text-color)") : ""}
          </div>
          ${a.comment ? `<p>${this._esc(a.comment)}</p>` : ""}
          <span class="muted">${this._esc(a.reporter)}${a.method ? " · " + this._esc(a.method.toLowerCase()) : ""}</span>
          <div style="display:flex;gap:20px;flex-wrap:wrap">
            <a class="open" href="${this._esc(a.url)}" target="_blank" rel="noopener">ÅPNE PÅ SKRIDSKONÄTET</a>
            ${a.map_links ? `<a class="open" href="${this._esc(a.map_links.norgeskart)}" target="_blank" rel="noopener">KART</a>` : ""}
          </div>
        </div>
        ${hist.length ? `<div class="hist"><div class="muted" style="padding:6px 0">Tidligere</div>
          ${hist.map((h) => `<a class="row" href="${this._esc(h.url)}" target="_blank" rel="noopener">
            <span class="dot" style="background:${h.color || "#9e9e9e"}"></span>
            <span class="name">${this._esc(h.name)}</span>
            <span class="muted">${this._esc(this._when(h.received))}</span></a>`).join("")}
        </div>` : ""}
      </ha-card>`;
  }
}

customElements.define("skridsko-card", SkridskoCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "skridsko-card",
  name: "Skridsko isobservasjoner",
  description: "Siste isobservasjon med bilde, status og tidligere observasjoner.",
});
