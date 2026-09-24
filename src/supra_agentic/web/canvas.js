/**
 * SUPRA Interactive Causal Vector Canvas (Vanilla JS HTML5 Canvas)
 * Zero external dependencies, responsive 60fps Bézier curve rendering.
 */

class CausalCanvas {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        
        this.nodes = [
            { id: 'inv', label: '01. Invariants', sub: 'Boundary Limits', x: 0.15, y: 0.5, color: '#4E75FF', radius: 36, status: 'STANDBY' },
            { id: 'strat_a', label: '02. Conservative', sub: 'Baseline Path', x: 0.45, y: 0.25, color: '#94A3B8', radius: 30, status: 'STANDBY' },
            { id: 'strat_b', label: '03. Orthogonal', sub: 'Decoupled Mesh', x: 0.45, y: 0.75, color: '#00FFCC', radius: 32, status: 'STANDBY' },
            { id: 'sandbox', label: '04–05. Gates', sub: 'Restricted + Docker', x: 0.75, y: 0.5, color: '#10B981', radius: 34, status: 'STANDBY' },
            { id: 'deliverable', label: '06. SHA-256', sub: 'Payload Integrity', x: 0.90, y: 0.5, color: '#00FFCC', radius: 28, status: 'STANDBY' }
        ];

        this.links = [
            { from: 0, to: 1, type: 'dashed' },
            { from: 0, to: 2, type: 'solid' },
            { from: 1, to: 3, type: 'dashed' },
            { from: 2, to: 3, type: 'solid' },
            { from: 3, to: 4, type: 'solid' }
        ];

        this.animFrame = 0;
        this.isDragging = false;
        this.dragNode = null;

        this.initEvents();
        this.resize();
        this.startRenderLoop();
    }

    resize() {
        if (!this.canvas) return;
        const rect = this.canvas.getBoundingClientRect();
        this.canvas.width = rect.width * window.devicePixelRatio;
        this.canvas.height = rect.height * window.devicePixelRatio;
        this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
        this.width = rect.width;
        this.height = rect.height;
    }

    initEvents() {
        window.addEventListener('resize', () => this.resize());
        
        this.canvas.addEventListener('mousedown', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            for (let node of this.nodes) {
                const nx = node.x * this.width;
                const ny = node.y * this.height;
                const dist = Math.hypot(mouseX - nx, mouseY - ny);
                if (dist <= node.radius) {
                    this.isDragging = true;
                    this.dragNode = node;
                    break;
                }
            }
        });

        window.addEventListener('mousemove', (e) => {
            if (!this.isDragging || !this.dragNode) return;
            const rect = this.canvas.getBoundingClientRect();
            this.dragNode.x = Math.max(0.08, Math.min(0.92, (e.clientX - rect.left) / this.width));
            this.dragNode.y = Math.max(0.12, Math.min(0.88, (e.clientY - rect.top) / this.height));
        });

        window.addEventListener('mouseup', () => {
            this.isDragging = false;
            this.dragNode = null;
        });
    }

    updateStage(stage, posture) {
        this.nodes.forEach(n => n.status = 'STANDBY');
        
        if (stage === 'RECEIVED' || stage === 'STRUCTURED') {
            this.nodes[0].status = 'ACTIVE';
        } else if (stage === 'STRATIFIED') {
            this.nodes[0].status = 'COMPLETED';
            this.nodes[1].status = 'ACTIVE';
            this.nodes[2].status = 'ACTIVE';
        } else if (stage === 'RESTRICTED_EXECUTION_VERIFIED') {
            this.nodes[0].status = 'COMPLETED';
            this.nodes[1].status = 'COMPLETED';
            this.nodes[2].status = 'COMPLETED';
            this.nodes[3].status = 'ACTIVE';
        } else if (stage === 'SECURE_SANDBOX_VERIFIED') {
            this.nodes[0].status = 'COMPLETED';
            this.nodes[1].status = 'COMPLETED';
            this.nodes[2].status = 'COMPLETED';
            this.nodes[3].status = 'COMPLETED';
            this.nodes[4].status = 'ACTIVE';
        } else if (stage === 'COMPLETED') {
            this.nodes.forEach(n => n.status = 'COMPLETED');
        }

        if (posture && posture.selected_candidate) {
            this.nodes[2].label = posture.selected_candidate.pathway_name.substring(0, 16) + '...';
            this.nodes[2].sub = posture.selected_candidate.paradigm_type;
        }
    }

    draw() {
        this.animFrame += 0.03;
        this.ctx.clearRect(0, 0, this.width, this.height);

        // Draw Links
        for (let link of this.links) {
            const n1 = this.nodes[link.from];
            const n2 = this.nodes[link.to];
            const x1 = n1.x * this.width;
            const y1 = n1.y * this.height;
            const x2 = n2.x * this.width;
            const y2 = n2.y * this.height;

            this.ctx.beginPath();
            this.ctx.moveTo(x1, y1);
            
            // Curved Bézier Control Points
            const cx = (x1 + x2) / 2;
            const cy = (y1 + y2) / 2 + (link.from === 0 && link.to === 1 ? -20 : 20);
            this.ctx.quadraticCurveTo(cx, cy, x2, y2);

            this.ctx.lineWidth = link.type === 'solid' ? 2 : 1.5;
            this.ctx.strokeStyle = (n1.status === 'COMPLETED' && n2.status !== 'STANDBY') ? '#00FFCC' : 'rgba(78, 117, 255, 0.35)';
            if (link.type === 'dashed') {
                this.ctx.setLineDash([4, 4]);
            } else {
                this.ctx.setLineDash([]);
            }
            this.ctx.stroke();
            this.ctx.setLineDash([]);
        }

        // Draw Nodes
        for (let node of this.nodes) {
            const nx = node.x * this.width;
            const ny = node.y * this.height;

            // Halo Effect for Active / Completed
            if (node.status === 'ACTIVE') {
                const pulse = Math.sin(this.animFrame * 2) * 4;
                this.ctx.beginPath();
                this.ctx.arc(nx, ny, node.radius + 6 + pulse, 0, Math.PI * 2);
                this.ctx.fillStyle = 'rgba(78, 117, 255, 0.2)';
                this.ctx.fill();
            } else if (node.status === 'COMPLETED') {
                this.ctx.beginPath();
                this.ctx.arc(nx, ny, node.radius + 4, 0, Math.PI * 2);
                this.ctx.fillStyle = 'rgba(0, 255, 204, 0.15)';
                this.ctx.fill();
            }

            // Node Circle
            this.ctx.beginPath();
            this.ctx.arc(nx, ny, node.radius, 0, Math.PI * 2);
            this.ctx.fillStyle = node.status === 'COMPLETED' ? '#0B1E19' : '#0E131F';
            this.ctx.fill();
            this.ctx.lineWidth = 2;
            this.ctx.strokeStyle = node.status === 'COMPLETED' ? '#00FFCC' : (node.status === 'ACTIVE' ? '#4E75FF' : 'rgba(255, 255, 255, 0.15)');
            this.ctx.stroke();

            // Label Text
            this.ctx.font = '600 11px Inter, sans-serif';
            this.ctx.fillStyle = node.status === 'COMPLETED' ? '#FFFFFF' : '#CBD5E1';
            this.ctx.textAlign = 'center';
            this.ctx.fillText(node.label, nx, ny - 2);

            this.ctx.font = '500 9px "JetBrains Mono", monospace';
            this.ctx.fillStyle = node.status === 'COMPLETED' ? '#00FFCC' : '#64748B';
            this.ctx.fillText(node.sub, nx, ny + 12);
        }
    }

    startRenderLoop() {
        const loop = () => {
            this.draw();
            requestAnimationFrame(loop);
        };
        requestAnimationFrame(loop);
    }
}

// Instantiate on page load
window.causalCanvasInstance = null;
document.addEventListener('DOMContentLoaded', () => {
    window.causalCanvasInstance = new CausalCanvas('causal-dag-canvas');
});
