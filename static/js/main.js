// static/js/main.js

document.addEventListener('DOMContentLoaded', () => {

    const App = {
        // --- 配置 ---
        config: {
            selectedClass: 'selected',
            playlistCardClass: 'playlist-card',
        },

        // --- 状态管理 ---
        state: {
            isDownloading: false,
            eventSource: null,
            currentSaveDir: '',
            currentPlaylistDir: '',
        },

        // --- UI 元素缓存 ---
        ui: {},

        // --- 初始化 ---
        init() {
            this.cacheDOMElements();
            this.bindEvents();
            this.syncDirectories();
            this.setupInitialUI();
            console.log("App initialized.");
        },

        cacheDOMElements() {
            this.ui.downloadForm = document.getElementById('download-form');
            this.ui.startBtn = document.getElementById('start-download-btn');
            this.ui.stopBtn = document.getElementById('stop-download-btn');
            this.ui.clearLogBtn = document.getElementById('clear-log-btn');
            this.ui.progressBar = document.getElementById('progress-bar');
            this.ui.statusLabel = document.getElementById('status-label');
            this.ui.logText = document.getElementById('log-text');
            this.ui.saveDir = document.getElementById('save-dir');
            this.ui.sortMusicDir = document.getElementById('sort-music-dir');
            this.ui.playlistUrl = document.getElementById('playlist-url');
            this.ui.primaryActions = document.getElementById('primary-actions');
            this.ui.retryActions = document.getElementById('retry-actions');
            this.ui.parseMethodContainer = document.getElementById('parse-method-container');
            this.ui.parseMethodInput = document.getElementById('parse-method');
            this.ui.lyricsOriginal = document.getElementById('download-lyrics-original');
            this.ui.lyricsTranslated = document.getElementById('download-lyrics-translated');
            this.ui.refreshPlaylistsBtn = document.getElementById('refresh-playlists-btn');
            this.ui.playlistListbox = document.getElementById('playlist-listbox');
            this.ui.sortPlaylistBtn = document.getElementById('sort-playlist-btn');
            this.ui.removeNumberingBtn = document.getElementById('remove-numbering-btn');
            this.ui.downloadPlaylistBtn = document.getElementById('download-playlist-btn');
            // [修复] 缓存正确的编号输入框
            this.ui.sortNumber = document.getElementById('sort-number');
            this.ui.retryDownloadBtn = document.getElementById('retry-download-btn');
            this.ui.backToDownloadBtn = document.getElementById('back-to-download-btn');
            this.ui.downloadTabBtn = document.getElementById('download-tab-btn');
            this.ui.sortTabBtn = document.getElementById('sort-tab-btn');
            
            // Toast
            this.ui.toastEl = document.getElementById('appToast');
            this.ui.toast = new bootstrap.Toast(this.ui.toastEl);
            this.ui.toastTitle = document.getElementById('toast-title');
            this.ui.toastBody = document.getElementById('toast-body');
        },

        bindEvents() {
            this.ui.downloadForm.addEventListener('submit', this.handleDownloadStart.bind(this));
            this.ui.stopBtn.addEventListener('click', this.handleDownloadStop.bind(this));
            this.ui.clearLogBtn.addEventListener('click', () => this.ui.logText.value = '');
            this.ui.saveDir.addEventListener('change', this.syncDirectories.bind(this));
            
            this.ui.parseMethodContainer.addEventListener('click', this.handleParseMethodSelect.bind(this));
            this.ui.lyricsOriginal.addEventListener('change', this.toggleTranslatedLyrics.bind(this));

            this.ui.sortTabBtn.addEventListener('shown.bs.tab', this.handleSortTabShown.bind(this));
            this.ui.refreshPlaylistsBtn.addEventListener('click', this.refreshPlaylists.bind(this));
            this.ui.playlistListbox.addEventListener('click', this.handlePlaylistSelect.bind(this));
            // [修复] 确保点击事件可以正常触发 handleSortAction
            this.ui.sortPlaylistBtn.addEventListener('click', () => this.handleSortAction('sort-playlist'));
            this.ui.removeNumberingBtn.addEventListener('click', () => this.handleSortAction('remove-numbering'));
            this.ui.downloadPlaylistBtn.addEventListener('click', this.handleDownloadSelectedPlaylist.bind(this));

            this.ui.retryDownloadBtn.addEventListener('click', this.handleRetryDownload.bind(this));
            this.ui.backToDownloadBtn.addEventListener('click', () => this.showActionButtons('primary'));
        },
        
        setupInitialUI() {
            this.toggleTranslatedLyrics();
            this.updateUI(false);
        },

        // --- 方法 ---

        /**
         * [修复] 修正了 showToast 的实现逻辑
         * @param {string} body - 消息内容
         * @param {string} title - 消息标题
         * @param {'success'|'warning'|'danger'} type - 消息类型
         */
        showToast(body, title = '提示', type = 'success') {
            this.ui.toastTitle.textContent = title;
            this.ui.toastBody.textContent = body;
            
            // 移除所有可能的背景色类
            this.ui.toastEl.classList.remove('text-bg-success', 'text-bg-warning', 'text-bg-danger');

            // 根据类型添加对应的背景色类
            switch(type) {
                case 'warning':
                    this.ui.toastEl.classList.add('text-bg-warning');
                    break;
                case 'danger':
                    this.ui.toastEl.classList.add('text-bg-danger');
                    break;
                default:
                    this.ui.toastEl.classList.add('text-bg-success');
                    break;
            }
            
            // 正确的显示方法
            this.ui.toast.show();
        },

        // UI 更新
        updateUI(isDownloading) {
            this.state.isDownloading = isDownloading;
            this.ui.startBtn.disabled = isDownloading;
            this.ui.stopBtn.disabled = !isDownloading;
            
            const formElements = this.ui.downloadForm.querySelectorAll('input, select, button[type="submit"]');
            formElements.forEach(el => {
                if (el.id !== 'stop-download-btn' && el.id !== 'clear-log-btn') {
                    el.disabled = isDownloading;
                }
            });

            if (!isDownloading) {
                this.resetProgress();
            }
        },
        
        resetProgress() {
            this.ui.progressBar.style.width = '0%';
            this.ui.progressBar.textContent = '0%';
            this.ui.statusLabel.textContent = '准备就绪';
        },
        
        showActionButtons(type) {
            if (type === 'retry') {
                this.ui.primaryActions.classList.add('d-none');
                this.ui.retryActions.classList.remove('d-none');
            } else {
                this.ui.primaryActions.classList.remove('d-none');
                this.ui.retryActions.classList.add('d-none');
            }
        },

        logMessage(message, type = 'info') {
            const timestamp = new Date().toLocaleTimeString();
            const prefix = {
                info: 'INFO',
                error: 'ERROR',
                success: 'SUCCESS'
            }[type];
            this.ui.logText.value += `[${timestamp} ${prefix}] ${message}\n`;
            this.ui.logText.scrollTop = this.ui.logText.scrollHeight;
        },

        // 下载逻辑
        handleDownloadStart(e) {
            e.preventDefault();
            this.state.currentSaveDir = this.ui.saveDir.value;
            this.showActionButtons('primary');

            fetch('/start-download', {
                method: 'POST',
                body: new FormData(this.ui.downloadForm)
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    this.logMessage('下载任务已启动...');
                    this.updateUI(true);
                    this.connectToStream();
                } else {
                    this.showToast(data.message || '启动下载失败', '错误', 'danger');
                }
            })
            .catch(err => this.showToast(`无法连接到服务器: ${err}`, '网络错误', 'danger'));
        },

        handleDownloadStop() {
            fetch('/stop-download', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    this.logMessage('已发送停止请求...');
                    this.ui.statusLabel.textContent = '正在停止...';
                } else {
                    this.showToast(data.message || '停止失败', '错误', 'danger');
                }
            });
        },
        
        handleRetryDownload() {
            const formData = new FormData(this.ui.downloadForm);
            
            fetch('/retry-failed-songs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    quality: formData.get('quality'),
                    download_lyrics: this.ui.lyricsOriginal.checked,
                    download_lyrics_translated: this.ui.lyricsTranslated.checked,
                    download_api: formData.get('download_api')
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    this.logMessage('开始重新下载失败的歌曲...');
                    this.updateUI(true);
                    this.connectToStream();
                } else {
                     this.showToast(data.message || '启动重新下载失败', '错误', 'danger');
                }
            })
            .catch(err => this.showToast(`无法连接到服务器: ${err}`, '网络错误', 'danger'));
        },

        // SSE 事件流
        connectToStream() {
            if (this.state.eventSource) this.state.eventSource.close();
            this.state.eventSource = new EventSource('/stream');

            this.state.eventSource.onmessage = event => {
                const data = JSON.parse(event.data);
                switch (data.type) {
                    case 'log':
                        this.logMessage(data.message);
                        if(data.message.includes("保存到:")){
                            this.state.currentPlaylistDir = data.message.split("保存到: ")[1];
                        }
                        break;
                    case 'progress':
                        const percent = Math.round(data.progress);
                        this.ui.progressBar.style.width = percent + '%';
                        this.ui.progressBar.textContent = percent + '%';
                        this.ui.statusLabel.textContent = data.status_text;
                        break;
                    case 'done':
                    case 'stopped':
                        this.handleDownloadEnd(data);
                        break;
                    case 'error':
                        this.logMessage(data.message, 'error');
                        this.showToast(data.message, '严重错误', 'danger');
                        this.handleDownloadEnd(data);
                        break;
                }
            };

            this.state.eventSource.onerror = () => {
                this.logMessage('与服务器的连接断开，请检查后端服务。', 'error');
                if(this.state.isDownloading) this.updateUI(false);
                this.state.eventSource.close();
            };
        },

        handleDownloadEnd(data) {
            this.logMessage(data.message, data.type === 'stopped' ? 'info' : 'success');
            this.ui.statusLabel.textContent = data.type === 'done' ? "任务完成!" : "任务已停止";
            this.updateUI(false);
            if (this.state.eventSource) this.state.eventSource.close();

            const title = `任务${data.type === 'done' ? '完成' : '停止'}`;
            const type = data.has_failed ? 'warning' : 'success';
            this.showToast(data.message, title, type);
            
            if (data.has_failed) {
                this.showActionButtons('retry');
            } else {
                this.showActionButtons('primary');
            }
        },

        // 其他表单逻辑
        syncDirectories() {
            this.ui.sortMusicDir.value = this.ui.saveDir.value;
        },

        handleParseMethodSelect(e) {
            const card = e.target.closest('.parse-method-card');
            if (!card) return;
            
            this.ui.parseMethodContainer.querySelectorAll('.parse-method-card').forEach(c => c.classList.remove(this.config.selectedClass));
            card.classList.add(this.config.selectedClass);
            this.ui.parseMethodInput.value = card.dataset.parseMethod;
        },
        
        toggleTranslatedLyrics() {
            this.ui.lyricsTranslated.disabled = !this.ui.lyricsOriginal.checked;
            if (!this.ui.lyricsOriginal.checked) {
                this.ui.lyricsTranslated.checked = false;
            }
        },
        
        // 歌单操作 Tab 逻辑
        handleSortTabShown(){
            if (this.ui.sortMusicDir.value) {
                this.refreshPlaylists();
            }
        },

        async refreshPlaylists() {
            const musicDir = this.ui.sortMusicDir.value;
            if (!musicDir) {
                this.showToast('请输入音乐目录', '提示', 'warning');
                return;
            }
            this.ui.playlistListbox.innerHTML = `<div class="col-12"><p class="text-muted mb-0">加载中...</p></div>`;

            try {
                const response = await fetch(`/get-playlists?path=${encodeURIComponent(musicDir)}`);
                const data = await response.json();
                this.renderPlaylists(data);
            } catch(err) {
                 this.ui.playlistListbox.innerHTML = `<div class="col-12"><p class="text-danger mb-0">刷新列表失败: ${err}</p></div>`;
            }
        },
        
        renderPlaylists(data) {
            this.ui.playlistListbox.innerHTML = '';
            if (data.playlists && data.playlists.length > 0) {
                const fragment = document.createDocumentFragment();
                data.playlists.forEach(p => {
                    const badgeColor = p.type === 'playlist' ? 'bg-info' : 'bg-warning text-dark';
                    const badgeText = p.type === 'playlist' ? '歌单' : '专辑';
                    const col = document.createElement('div');
                    col.className = 'col-md-6 col-lg-4';
                    col.innerHTML = `
                        <div class="card ${this.config.playlistCardClass}" data-playlist-name="${p.name}" data-playlist-type="${p.type}">
                            <div class="card-body p-2 d-flex justify-content-between align-items-center">
                                <span class="text-truncate flex-grow-1" title="${p.name}">${p.name}</span>
                                <span class="badge ${badgeColor}">${badgeText}</span>
                            </div>
                        </div>`;
                    fragment.appendChild(col);
                });
                this.ui.playlistListbox.appendChild(fragment);
            } else {
                this.ui.playlistListbox.innerHTML = `<div class="col-12"><p class="text-muted mb-0">${data.message || '未找到歌单'}</p></div>`;
            }
        },
        
        handlePlaylistSelect(e) {
            const card = e.target.closest(`.${this.config.playlistCardClass}`);
            if (!card) return;

            const currentlySelected = this.ui.playlistListbox.querySelector(`.${this.config.selectedClass}`);
            if (currentlySelected) currentlySelected.classList.remove(this.config.selectedClass);
            
            card.classList.add(this.config.selectedClass);
        },
        
        getSelectedPlaylist() {
            const selectedCard = this.ui.playlistListbox.querySelector(`.${this.config.selectedClass}`);
            if (!selectedCard) {
                this.showToast('请先选择一个歌单', '提示', 'warning');
                return null;
            }
            return {
                name: selectedCard.dataset.playlistName,
                type: selectedCard.dataset.playlistType,
            };
        },
        
        async handleSortAction(action) {
            const selectedPlaylist = this.getSelectedPlaylist();
            if (!selectedPlaylist) return;

            let payload = {
                base_dir: this.ui.sortMusicDir.value,
                playlist_name: selectedPlaylist.name,
            };
            if (action === 'sort-playlist') {
                // [修复] 从正确的输入框获取值，并发送给后端
                payload.start_number = parseInt(this.ui.sortNumber.value, 10);
            }

            try {
                const response = await fetch(`/${action}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                const toastType = data.status === 'success' ? 'success' : 'danger';
                this.showToast(data.message, '操作结果', toastType);
            } catch(err) {
                 this.showToast(`操作失败: ${err}`, '网络错误', 'danger');
            }
        },
        
        async handleDownloadSelectedPlaylist() {
            const selectedPlaylist = this.getSelectedPlaylist();
            if (!selectedPlaylist) return;
            
            const path = this.ui.sortMusicDir.value;
            const name = selectedPlaylist.name;

            try {
                const response = await fetch(`/get-playlist-id?path=${encodeURIComponent(path)}&playlist=${encodeURIComponent(name)}`);
                const data = await response.json();
                if (data.playlist_id) {
                    this.ui.playlistUrl.value = data.playlist_id;
                    const method = selectedPlaylist.type === 'album' ? 'album' : 'playlist';
                    this.ui.parseMethodContainer.querySelector(`[data-parse-method="${method}"]`).click();
                    
                    const tab = new bootstrap.Tab(this.ui.downloadTabBtn);
                    tab.show();
                    this.showToast('已将歌单ID填充到下载页面', '操作成功', 'success');
                } else {
                    this.showToast(`无法获取歌单ID: ${data.message || '未知错误'}`, '错误', 'danger');
                }
            } catch(err) {
                 this.showToast(`获取歌单ID失败: ${err}`, '网络错误', 'danger');
            }
        }
    };

    App.init();
});