class CausalCanvas {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");
    this.nodes = [];
    this.links = [];
    this.stage = "STANDBY";
    this.frame = 0;
    this.dragNode = null;
    this.resize();
    this.bind();
    this.setPosture(null);
    this.loop();
  }

  bind() {
    window.addEventListener("resize", () => this.resize());
    this.canvas.addEventListener("pointerdown", (event) => {
      const p = this.pointer(event);
      this.dragNode = this.nodes.find(node => Math.hypot(p.x - node.x * this.width, p.y - node.y * this.height) <= node.radius + 7) || null;
      if (this.dragNode) this.canvas.setPointerCapture(event.pointerId);
    });
    this.canvas.addEventListener("pointermove", (event) => {
      if (!this.dragNode) return;
      const p = this.pointer(event);
      this.dragNode.x = Math.max(.08, Math.min(.92, p.x / this.width));
      this.dragNode.y = Math.max(.12, Math.min(.88, p.y / this.height));
    });
    this.canvas.addEventListener("pointerup", () => { this.dragNode = null; });
    this.canvas.addEventListener("pointercancel", () => { this.dragNode = null; });
  }

  pointer(event) {
    const rect = this.canvas.getBoundingClientRect();
    return {x:event.clientX - rect.left, y:event.clientY - rect.top};
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    this.canvas.width = Math.max(1, Math.round(rect.width * ratio));
    this.canvas.height = Math.max(1, Math.round(rect.height * ratio));
    this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.width = rect.width;
    this.height = rect.height;
  }

  setPosture(posture) {
    const decomp = posture && posture.decomposition ? posture.decomposition : {};
    const invariants = Array.isArray(decomp.invariants) ? decomp.invariants.slice(0, 3) : [];
    const candidates = posture && Array.isArray(posture.candidates) ? posture.candidates.slice(0, 4) : [];
    const selected = posture && posture.selected_candidate ? posture.selected_candidate : null;
    const verdict = posture && posture.verification ? posture.verification.verdict : "NOT_EVALUATED";

    const invNodes = invariants.length ? invariants.map((text, i) => ({
      id:`inv-${i}`, kind:"invariant", label:`I${i + 1}`, sub:this.short(text, 22),
      x:.14, y:.24 + i * .25, radius:22
    })) : [
      {id:"objective", kind:"invariant", label:"OBJ", sub:"Objetivo / invariantes", x:.14, y:.5, radius:25}
    ];

    const stratY = candidates.length > 1 ? candidates.map((_, i) => .17 + i * (.66 / (candidates.length - 1))) : [.5];
    const stratNodes = candidates.length ? candidates.map((c, i) => ({
      id:`strategy-${i}`, kind:c.is_selected ? "selected" : "strategy",
      label:c.is_selected ? "S★" : `S${i + 1}`,
      sub:this.short(c.pathway_name, 23), x:.45, y:stratY[i], radius:c.is_selected ? 27 : 23
    })) : [
      {id:"strategy", kind:"strategy", label:"S", sub:"Estrategias", x:.45, y:.5, radius:25}
    ];

    const verifyNode = {id:"verify", kind:verdict === "FAIL" ? "fail" : "verify", label:"V", sub:verdict, x:.72, y:.39, radius:27};
    const sandboxNode = {id:"sandbox", kind:"verify", label:"SB", sub:"Sandbox", x:.72, y:.66, radius:24};
    const outputNode = {id:"output", kind:"output", label:"D", sub:selected ? this.short(selected.paradigm_type, 16) : "Dossier", x:.9, y:.52, radius:28};

    this.nodes = [...invNodes, ...stratNodes, verifyNode, sandboxNode, outputNode];
    this.links = [];
    invNodes.forEach(inv => stratNodes.forEach(strat => this.links.push({from:inv.id, to:strat.id, dashed:true})));
    stratNodes.forEach(strat => {
      this.links.push({from:strat.id, to:"verify", dashed:!strat.kind.includes("selected")});
      this.links.push({from:strat.id, to:"sandbox", dashed:true});
    });
    this.links.push({from:"verify", to:"output", dashed:false});
    this.links.push({from:"sandbox", to:"output", dashed:false});
    this.stage = posture ? posture.stage : "STANDBY";
  }

  updateStage(stage, posture) {
    this.stage = stage || "STANDBY";
    if (posture) this.setPosture(posture);
  }

  short(value, max) {
    const text = String(value || "");
    return text.length > max ? text.slice(0, max - 1) + "…" : text;
  }

  palette(kind) {
    if (kind === "selected") return {stroke:"#7c4dff", glow:"rgba(112,56,255,.32)", fill:"#241056", text:"#f4eaff"};
    if (kind === "verify") return {stroke:"#26dbbd", glow:"rgba(38,219,189,.23)", fill:"#07352f", text:"#d9fff7"};
    if (kind === "fail") return {stroke:"#ff5d78", glow:"rgba(255,93,120,.25)", fill:"#3a1020", text:"#ffe2e8"};
    if (kind === "output") return {stroke:"#b93cff", glow:"rgba(185,60,255,.28)", fill:"#271046", text:"#f4e7ff"};
    if (kind === "strategy") return {stroke:"#4c8cff", glow:"rgba(51,111,255,.22)", fill:"#0a2452", text:"#e1edff"};
    return {stroke:"#28cfff", glow:"rgba(40,207,255,.22)", fill:"#072e50", text:"#e0faff"};
  }

  drawLink(link) {
    const from = this.nodes.find(n => n.id === link.from);
    const to = this.nodes.find(n => n.id === link.to);
    if (!from || !to) return;
    const x1 = from.x * this.width, y1 = from.y * this.height;
    const x2 = to.x * this.width, y2 = to.y * this.height;
    const cp1x = x1 + (x2 - x1) * .45;
    const cp2x = x1 + (x2 - x1) * .55;

    this.ctx.save();
    this.ctx.beginPath();
    this.ctx.moveTo(x1, y1);
    this.ctx.bezierCurveTo(cp1x, y1, cp2x, y2, x2, y2);
    this.ctx.strokeStyle = link.dashed ? "rgba(83,145,255,.42)" : "rgba(42,218,211,.72)";
    this.ctx.lineWidth = link.dashed ? 1 : 1.7;
    if (link.dashed) this.ctx.setLineDash([4,4]);
    this.ctx.stroke();
    this.ctx.setLineDash([]);

    const angle = Math.atan2(y2 - y1, x2 - x1);
    const ax = x2 - Math.cos(angle) * (to.radius + 3);
    const ay = y2 - Math.sin(angle) * (to.radius + 3);
    this.ctx.beginPath();
    this.ctx.moveTo(ax, ay);
    this.ctx.lineTo(ax - 6 * Math.cos(angle - .55), ay - 6 * Math.sin(angle - .55));
    this.ctx.lineTo(ax - 6 * Math.cos(angle + .55), ay - 6 * Math.sin(angle + .55));
    this.ctx.closePath();
    this.ctx.fillStyle = link.dashed ? "#6ea8ff" : "#47ebd1";
    this.ctx.fill();
    this.ctx.restore();
  }

  drawNode(node) {
    const x = node.x * this.width, y = node.y * this.height;
    const p = this.palette(node.kind);
    const pulse = 1 + Math.sin(this.frame * 2 + x) * 1.8;

    this.ctx.save();
    const grad = this.ctx.createRadialGradient(x, y, node.radius * .35, x, y, node.radius + 12 + pulse);
    grad.addColorStop(0, p.glow);
    grad.addColorStop(1, "rgba(0,0,0,0)");
    this.ctx.fillStyle = grad;
    this.ctx.beginPath();
    this.ctx.arc(x, y, node.radius + 13 + pulse, 0, Math.PI * 2);
    this.ctx.fill();

    this.ctx.beginPath();
    this.ctx.arc(x, y, node.radius, 0, Math.PI * 2);
    this.ctx.fillStyle = p.fill;
    this.ctx.fill();
    this.ctx.lineWidth = node.kind === "selected" || node.kind === "output" ? 2.4 : 1.7;
    this.ctx.strokeStyle = p.stroke;
    this.ctx.shadowColor = p.stroke;
    this.ctx.shadowBlur = 12;
    this.ctx.stroke();
    this.ctx.shadowBlur = 0;

    this.ctx.fillStyle = p.text;
    this.ctx.font = "700 12px Inter, Segoe UI, sans-serif";
    this.ctx.textAlign = "center";
    this.ctx.fillText(node.label, x, y + 4);
    this.ctx.font = "500 9px Inter, Segoe UI, sans-serif";
    this.ctx.fillStyle = "#a7bce1";
    this.ctx.fillText(node.sub, x, y + node.radius + 14);
    this.ctx.restore();
  }

  draw() {
    if (!this.width || !this.height) return;
    this.frame += .028;
    this.ctx.clearRect(0,0,this.width,this.height);

    const glow = this.ctx.createRadialGradient(this.width*.55,this.height*.48,20,this.width*.55,this.height*.48,this.width*.55);
    glow.addColorStop(0,"rgba(14,67,156,.13)");
    glow.addColorStop(1,"rgba(0,0,0,0)");
    this.ctx.fillStyle = glow;
    this.ctx.fillRect(0,0,this.width,this.height);

    this.links.forEach(link => this.drawLink(link));
    this.nodes.forEach(node => this.drawNode(node));
  }

  loop() {
    this.draw();
    requestAnimationFrame(() => this.loop());
  }
}

window.causalCanvasInstance = null;
document.addEventListener("DOMContentLoaded", () => {
  window.causalCanvasInstance = new CausalCanvas("causal-dag-canvas");
});
