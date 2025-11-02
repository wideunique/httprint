// HTTPrint - Modern file upload interface
// Supports images and documents (PDF, Office)

(function() {
    'use strict';

    // State management
    const state = {
        selectedType: null,
        files: [],
        isUploading: false
    };

    // File type configurations
    const fileTypes = {
        images: {
            accept: '.jpg,.jpeg,.png,.gif,.bmp,.tiff',
            multiple: true,
            icon: '🖼️',
            hint: '支持的格式：JPG, PNG, GIF, BMP, TIFF（可上传多张，自动合并为 PDF）'
        },
        documents: {
            accept: '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx',
            multiple: false,
            icon: '📄',
            hint: '支持的格式：PDF, Word, Excel, PowerPoint（只能上传一个文件）'
        }
    };

    // DOM elements
    let elements = {};

    // Initialize
    function init() {
        // Get DOM elements
        elements = {
            fileTypeButtons: document.querySelectorAll('.file-type-btn'),
            uploadArea: document.getElementById('upload-area'),
            fileInput: document.getElementById('file-input'),
            uploadHint: document.getElementById('upload-hint'),
            imagePreviewGrid: document.getElementById('image-preview-grid'),
            fileInfoDisplay: document.getElementById('file-info-display'),
            fileIcon: document.getElementById('file-icon'),
            fileName: document.getElementById('file-name'),
            fileMeta: document.getElementById('file-meta'),
            removeFileBtn: document.getElementById('remove-file-btn'),
            uploadProgress: document.getElementById('upload-progress'),
            progressBar: document.getElementById('progress-bar'),
            copiesGroup: document.getElementById('copies-group'),
            copiesInput: document.getElementById('copies'),
            pagesGroup: document.getElementById('pages-group'),
            pagesInput: document.getElementById('pages'),
            doubleSidedGroup: document.getElementById('double-sided-group'),
            doubleSidedInput: document.getElementById('double-sided'),
            actionButtons: document.getElementById('action-buttons'),
            printBtn: document.getElementById('print-btn'),
            printBtnText: document.getElementById('print-btn-text'),
            printSpinner: document.getElementById('print-spinner'),
            clearBtn: document.getElementById('clear-btn'),
            infoAlert: document.getElementById('info-alert')
        };

        // Bind events
        bindEvents();
    }

    // Bind all event listeners
    function bindEvents() {
        // File type selection
        elements.fileTypeButtons.forEach(btn => {
            btn.addEventListener('click', () => selectFileType(btn.dataset.type));
        });

        // Upload area click
        elements.uploadArea.addEventListener('click', () => elements.fileInput.click());

        // File input change
        elements.fileInput.addEventListener('change', handleFileSelect);

        // Drag and drop
        elements.uploadArea.addEventListener('dragover', handleDragOver);
        elements.uploadArea.addEventListener('dragleave', handleDragLeave);
        elements.uploadArea.addEventListener('drop', handleDrop);

        // Remove file button
        elements.removeFileBtn.addEventListener('click', clearFiles);

        // Print button
        elements.printBtn.addEventListener('click', uploadFiles);

        // Clear button
        elements.clearBtn.addEventListener('click', clearFiles);
    }

    // Select file type
    function selectFileType(type) {
        state.selectedType = type;
        const config = fileTypes[type];

        // Update UI
        elements.fileTypeButtons.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.type === type);
        });

        // Configure file input
        elements.fileInput.accept = config.accept;
        elements.fileInput.multiple = config.multiple;

        // Update upload hint
        elements.uploadHint.textContent = config.hint;

        // Show upload area
        elements.uploadArea.style.display = 'block';
        elements.infoAlert.style.display = 'none';

        // Clear previous files
        clearFiles();
    }

    // Handle file selection
    function handleFileSelect(e) {
        const files = Array.from(e.target.files);
        if (files.length > 0) {
            addFiles(files);
        }
    }

    // Handle drag over
    function handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        elements.uploadArea.classList.add('dragover');
    }

    // Handle drag leave
    function handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        elements.uploadArea.classList.remove('dragover');
    }

    // Handle drop
    function handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        elements.uploadArea.classList.remove('dragover');

        const files = Array.from(e.dataTransfer.files);
        if (files.length > 0) {
            // Validate file types
            const config = fileTypes[state.selectedType];
            const acceptedExtensions = config.accept.split(',').map(ext => ext.trim());

            const validFiles = files.filter(file => {
                const ext = '.' + file.name.split('.').pop().toLowerCase();
                return acceptedExtensions.includes(ext);
            });

            if (validFiles.length !== files.length) {
                showToast('部分文件格式不支持，已自动过滤', 'warning');
            }

            if (validFiles.length > 0) {
                addFiles(validFiles);
            }
        }
    }

    // Add files to state
    function addFiles(files) {
        const config = fileTypes[state.selectedType];

        if (!config.multiple && files.length > 1) {
            showToast('此文件类型只支持单个文件上传', 'error');
            return;
        }

        if (!config.multiple) {
            state.files = [files[0]];
        } else {
            state.files = state.files.concat(files);
        }

        updateUI();
    }

    // Update UI based on current state
    function updateUI() {
        if (state.files.length === 0) {
            // No files selected
            elements.uploadArea.style.display = 'block';
            elements.imagePreviewGrid.style.display = 'none';
            elements.fileInfoDisplay.style.display = 'none';
            elements.copiesGroup.style.display = 'none';
            elements.pagesGroup.style.display = 'none';
            elements.doubleSidedGroup.style.display = 'none';
            elements.actionButtons.style.display = 'none';
            elements.printBtn.disabled = true;
            return;
        }

        // Hide upload area
        elements.uploadArea.style.display = 'none';

        // Show appropriate UI based on file type
        if (state.selectedType === 'images' && state.files.length > 1) {
            // Multiple images - show grid
            renderImageGrid();
            elements.imagePreviewGrid.style.display = 'grid';
            elements.fileInfoDisplay.style.display = 'none';
        } else {
            // Single file - show info display
            renderFileInfo();
            elements.imagePreviewGrid.style.display = 'none';
            elements.fileInfoDisplay.style.display = 'block';
        }

        // Show copies and action buttons
        elements.copiesGroup.style.display = 'block';
        elements.pagesGroup.style.display = 'block';
        elements.doubleSidedGroup.style.display = 'block';
        elements.actionButtons.style.display = 'flex';
        elements.printBtn.disabled = false;
    }

    // Render image grid for multiple images
    function renderImageGrid() {
        elements.imagePreviewGrid.innerHTML = '';

        state.files.forEach((file, index) => {
            const item = document.createElement('div');
            item.className = 'image-preview-item';
            item.dataset.index = index;

            // Create image preview
            const img = document.createElement('img');
            const reader = new FileReader();
            reader.onload = (e) => {
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);

            // Create info section
            const info = document.createElement('div');
            info.className = 'info';

            const filename = document.createElement('div');
            filename.className = 'filename';
            filename.textContent = file.name;
            filename.title = file.name;

            const filesize = document.createElement('div');
            filesize.className = 'filesize';
            filesize.textContent = formatFileSize(file.size);

            info.appendChild(filename);
            info.appendChild(filesize);

            // Create remove button
            const removeBtn = document.createElement('button');
            removeBtn.className = 'remove-btn';
            removeBtn.innerHTML = '×';
            removeBtn.onclick = (e) => {
                e.stopPropagation();
                removeFile(index);
            };

            // Create order badge
            const orderBadge = document.createElement('div');
            orderBadge.className = 'order-badge';
            orderBadge.textContent = index + 1;

            item.appendChild(img);
            item.appendChild(info);
            item.appendChild(removeBtn);
            item.appendChild(orderBadge);

            elements.imagePreviewGrid.appendChild(item);
        });

        // Initialize Sortable for drag and drop reordering
        if (window.Sortable) {
            new Sortable(elements.imagePreviewGrid, {
                animation: 150,
                ghostClass: 'sortable-ghost',
                onEnd: function(evt) {
                    // Reorder files array
                    const item = state.files.splice(evt.oldIndex, 1)[0];
                    state.files.splice(evt.newIndex, 0, item);
                    updateUI();
                }
            });
        }
    }

    // Render file info for single file
    function renderFileInfo() {
        const file = state.files[0];
        const ext = file.name.split('.').pop().toLowerCase();

        // Set icon based on file type
        let icon = '📄';
        if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff'].includes(ext)) {
            icon = '🖼️';
        } else if (['doc', 'docx'].includes(ext)) {
            icon = '📝';
        } else if (['xls', 'xlsx'].includes(ext)) {
            icon = '📊';
        } else if (['ppt', 'pptx'].includes(ext)) {
            icon = '📽️';
        }

        elements.fileIcon.textContent = icon;
        elements.fileName.textContent = file.name;
        elements.fileMeta.textContent = `大小: ${formatFileSize(file.size)}`;
    }

    // Remove file by index
    function removeFile(index) {
        state.files.splice(index, 1);
        updateUI();
    }

    // Clear all files
    function clearFiles() {
        state.files = [];
        elements.fileInput.value = '';
        elements.pagesInput.value = '';
        elements.doubleSidedInput.checked = true;
        updateUI();
    }

    // Upload files to server
    function uploadFiles() {
        if (state.isUploading || state.files.length === 0) {
            return;
        }

        const pages = elements.pagesInput.value.trim();
        if (pages && !/^[0-9,\-\s]+$/.test(pages)) {
            showToast('页码格式错误，请使用数字、逗号和连字符', 'error');
            elements.pagesInput.focus();
            return;
        }

        state.isUploading = true;

        // Disable buttons
        elements.printBtn.disabled = true;
        elements.clearBtn.disabled = true;
        elements.printBtnText.style.display = 'none';
        elements.printSpinner.style.display = 'inline-block';

        // Show progress bar
        elements.uploadProgress.classList.add('active');
        updateProgress(0, '准备上传...');

        // Create FormData
        const formData = new FormData();
        const copies = elements.copiesInput.value;
        const doubleSided = elements.doubleSidedInput.checked;

        // Add files to FormData
        state.files.forEach(file => {
            formData.append('file', file);
        });
        formData.append('copies', copies);
        if (pages) {
            formData.append('pages', pages);
        }
        formData.append('double_sided', doubleSided ? 'true' : 'false');

        // Upload using XMLHttpRequest for progress tracking
        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percentComplete = Math.round((e.loaded / e.total) * 100);
                updateProgress(percentComplete, `上传中... ${percentComplete}%`);
            }
        });

        xhr.addEventListener('load', () => {
            if (xhr.status === 200) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    handleUploadSuccess(response);
                } catch (e) {
                    handleUploadError('服务器响应格式错误');
                }
            } else {
                try {
                    const response = JSON.parse(xhr.responseText);
                    handleUploadError(response.message || '上传失败');
                } catch (e) {
                    handleUploadError(`上传失败 (HTTP ${xhr.status})`);
                }
            }
        });

        xhr.addEventListener('error', () => {
            handleUploadError('网络错误，请检查连接');
        });

        xhr.addEventListener('abort', () => {
            handleUploadError('上传已取消');
        });

        xhr.open('POST', '/api/upload');
        xhr.send(formData);
    }

    // Handle upload success
    function handleUploadSuccess(response) {
        state.isUploading = false;

        // Hide progress bar
        elements.uploadProgress.classList.remove('active');

        // Build success message
        let message = response.message || '文件已发送到打印机';

        if (response.details) {
            const details = [];
            if (response.details.total_images) {
                details.push(`图片数量: ${response.details.total_images}`);
            }
            if (response.details.original_format) {
                details.push(`原始格式: ${response.details.original_format.toUpperCase()}`);
            }
            if (response.details.total_pages) {
                details.push(`总页数: ${response.details.total_pages}`);
            }
            if (response.details.page_ranges) {
                details.push(`打印页码: ${response.details.page_ranges}`);
            }
            if (Object.prototype.hasOwnProperty.call(response.details, 'double_sided')) {
                details.push(`双面打印: ${response.details.double_sided ? '是' : '否'}`);
            }

            if (details.length > 0) {
                message += '<br><small>' + details.join(' | ') + '</small>';
            }
        }

        showToast(message, 'success', false);

        // Reset UI
        clearFiles();
        elements.copiesInput.value = 1;
        elements.pagesInput.value = '';
        elements.doubleSidedInput.checked = true;
        elements.printBtnText.style.display = 'inline';
        elements.printSpinner.style.display = 'none';
        elements.clearBtn.disabled = false;
    }

    // Handle upload error
    function handleUploadError(message) {
        state.isUploading = false;

        // Hide progress bar
        elements.uploadProgress.classList.remove('active');

        // Show error message
        showToast(message, 'error');

        // Re-enable buttons
        elements.printBtn.disabled = false;
        elements.clearBtn.disabled = false;
        elements.printBtnText.style.display = 'inline';
        elements.printSpinner.style.display = 'none';
    }

    // Update progress bar
    function updateProgress(percent, text) {
        elements.progressBar.style.width = percent + '%';
        elements.progressBar.textContent = text;
    }

    // Format file size
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }

    // Show toast notification
    function showToast(message, type = 'info', autoHide = true) {
        const config = {
            text: message,
            heading: type === 'success' ? '成功！' : type === 'error' ? '错误！' : type === 'warning' ? '警告！' : '提示',
            icon: type,
            showHideTransition: 'fade',
            allowToastClose: true,
            hideAfter: autoHide ? 5000 : false,
            stack: 5,
            position: 'top-center'
        };

        if (window.$ && $.toast) {
            $.toast(config);
        } else {
            alert(config.heading + '\n' + message);
        }
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
