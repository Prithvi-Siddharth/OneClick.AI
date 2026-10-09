/**
 * OneClick.AI - Client Compute Manager
 * Coordinates in-browser WebAssembly ML workloads via Web Worker.
 */

class ClientComputeManager {
    constructor() {
        this.worker = null;
        this.isReady = false;
        this.callbacks = new Map();
        this.initPromise = null;
        this.statusListeners = [];
    }

    init() {
        if (this.initPromise) return this.initPromise;

        this.initPromise = new Promise((resolve, reject) => {
            try {
                this.worker = new Worker('/static/js/pyodide-worker.js');

                this.worker.onmessage = (event) => {
                    const data = event.data;

                    if (data.type === 'STATUS') {
                        this.notifyStatus(data.message, 'loading');
                    } else if (data.type === 'READY') {
                        this.isReady = true;
                        this.notifyStatus('⚡ Client WebAssembly ML Engine Ready', 'ready');
                        resolve();
                    } else if (data.type === 'PROGRESS') {
                        const cb = this.callbacks.get('progress');
                        if (cb) cb(data);
                    } else if (data.type === 'TRAIN_COMPLETE') {
                        const cb = this.callbacks.get('train');
                        if (cb) {
                            cb.resolve(data.result);
                            this.callbacks.delete('train');
                        }
                    } else if (data.type === 'EDA_COMPLETE') {
                        const cb = this.callbacks.get('eda');
                        if (cb) {
                            cb.resolve(data.stats);
                            this.callbacks.delete('eda');
                        }
                    } else if (data.type === 'ERROR') {
                        this.notifyStatus('Compute Engine Error: ' + data.error, 'error');
                        const trainCb = this.callbacks.get('train');
                        if (trainCb) {
                            trainCb.reject(new Error(data.error));
                            this.callbacks.delete('train');
                        }
                        const edaCb = this.callbacks.get('eda');
                        if (edaCb) {
                            edaCb.reject(new Error(data.error));
                            this.callbacks.delete('eda');
                        }
                    }
                };

                this.worker.onerror = (err) => {
                    console.error('Pyodide Worker Error:', err);
                    this.notifyStatus('Worker initialization failed', 'error');
                    reject(err);
                };
            } catch (err) {
                reject(err);
            }
        });

        return this.initPromise;
    }

    onStatusChange(fn) {
        this.statusListeners.push(fn);
    }

    notifyStatus(msg, state) {
        this.statusListeners.forEach(fn => fn(msg, state));
        const badge = document.getElementById('client-compute-badge');
        if (badge) {
            badge.innerText = msg;
            badge.className = 'compute-badge compute-badge-' + state;
        }
    }

    async train(params, onProgress) {
        await this.init();
        if (onProgress) this.callbacks.set('progress', onProgress);

        return new Promise((resolve, reject) => {
            this.callbacks.set('train', { resolve, reject });
            this.worker.postMessage({
                action: 'TRAIN',
                payload: params
            });
        });
    }

    async runEDA(csvData) {
        await this.init();
        return new Promise((resolve, reject) => {
            this.callbacks.set('eda', { resolve, reject });
            this.worker.postMessage({
                action: 'EDA',
                payload: csvData
            });
        });
    }
}

// Global instance
window.OneClickCompute = new ClientComputeManager();

// Automatically start warm-up when the page loads
if (typeof window !== 'undefined') {
    window.addEventListener('DOMContentLoaded', () => {
        // Create an unobtrusive compute badge in the corner
        const badgeContainer = document.createElement('div');
        badgeContainer.id = 'client-compute-badge-container';
        badgeContainer.style.cssText = `
            position: fixed;
            bottom: 15px;
            left: 20px;
            z-index: 9000;
            font-family: inherit;
            font-size: 0.78rem;
            pointer-events: none;
        `;
        badgeContainer.innerHTML = `
            <div id="client-compute-badge" style="
                background: rgba(30, 41, 59, 0.85);
                backdrop-filter: blur(8px);
                color: #94a3b8;
                border: 1px solid rgba(148, 163, 184, 0.2);
                border-radius: 20px;
                padding: 6px 14px;
                display: flex;
                align-items: center;
                gap: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                transition: all 0.3s ease;
            ">
                <span class="compute-dot" style="width: 8px; height: 8px; border-radius: 50%; background: #f59e0b; display: inline-block;"></span>
                <span>Initializing In-Browser Engine...</span>
            </div>
        `;
        document.body.appendChild(badgeContainer);

        window.OneClickCompute.onStatusChange((msg, state) => {
            const badge = document.getElementById('client-compute-badge');
            if (!badge) return;
            const dot = badge.querySelector('.compute-dot');
            badge.querySelector('span:last-child').textContent = msg;
            if (state === 'ready') {
                badge.style.color = '#34d399';
                badge.style.borderColor = 'rgba(52, 211, 153, 0.3)';
                if (dot) dot.style.background = '#10b981';
            } else if (state === 'error') {
                badge.style.color = '#f87171';
                badge.style.borderColor = 'rgba(248, 113, 113, 0.3)';
                if (dot) dot.style.background = '#ef4444';
            }
        });

        // Initialize engine in background
        window.OneClickCompute.init().catch(err => {
            console.log('Client compute background warm-up deferred or error:', err);
        });
    });
}
