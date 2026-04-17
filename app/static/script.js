document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('plate-form');
    const tabBtns = document.querySelectorAll('.tab-btn');
    const kleInput = document.getElementById('kle_file');
    const pcbInput = document.getElementById('pcb_file');
    const kleName = document.getElementById('kle-name');
    const pcbName = document.getElementById('pcb-name');
    const kleDropZone = document.getElementById('kle-drop-zone');
    const pcbDropZone = document.getElementById('pcb-drop-zone');
    const kleOptions = document.getElementById('kle-options');
    const pcbOnlyGroups = document.querySelectorAll('.pcb-only');
    const submitBtn = document.getElementById('submit-btn');
    const results = document.getElementById('results');
    const errorMsg = document.getElementById('error-message');
    const downloadLink = document.getElementById('download-link');

    let currentTab = 'kle';

    // KLE Input Mode Toggle
    const kleModeRadios = document.querySelectorAll('input[name="kle_input_mode"]');
    const kleFileInputDiv = document.getElementById('kle-file-input');
    const kleTextInputDiv = document.getElementById('kle-text-input');
    const kleTextarea = document.getElementById('kle_text');

    kleModeRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            if (e.target.value === 'file') {
                kleFileInputDiv.classList.remove('hidden');
                kleTextInputDiv.classList.add('hidden');
                kleTextarea.value = ''; // clear text if switching to file
            } else {
                kleFileInputDiv.classList.add('hidden');
                kleTextInputDiv.classList.remove('hidden');
                kleInput.value = ''; // clear file if switching to text
                kleName.textContent = '';
            }
        });
    });

    // Tab Switching
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentTab = btn.dataset.tab;

            if (currentTab === 'kle') {
                kleOptions.classList.remove('hidden');
                pcbOnlyGroups.forEach(el => el.classList.add('hidden'));
            } else {
                kleOptions.classList.add('hidden');
                pcbOnlyGroups.forEach(el => el.classList.remove('hidden'));
            }
            results.classList.add('hidden');
            errorMsg.classList.add('hidden');
        });
    });

    // File Input Styling
    const handleFileSelect = (input, nameEl) => {
        if (input.files && input.files.length > 0) {
            nameEl.textContent = `Selected: ${input.files[0].name}`;
        }
    };

    kleInput.addEventListener('change', () => handleFileSelect(kleInput, kleName));
    pcbInput.addEventListener('change', () => handleFileSelect(pcbInput, pcbName));

    // Drag and Drop
    const setupDropZone = (zone, input, nameEl) => {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            zone.addEventListener(eventName, e => {
                e.preventDefault();
                e.stopPropagation();
            }, false);
        });

        zone.addEventListener('dragover', () => zone.classList.add('drag-over'));
        ['dragleave', 'drop'].forEach(eventName => {
            zone.addEventListener(eventName, () => zone.classList.remove('drag-over'));
        });

        zone.addEventListener('drop', e => {
            const dt = e.dataTransfer;
            input.files = dt.files;
            handleFileSelect(input, nameEl);
        });
    };

    setupDropZone(kleDropZone, kleInput, kleName);
    setupDropZone(pcbDropZone, pcbInput, pcbName);

    // Form Submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        submitBtn.disabled = true;
        submitBtn.textContent = 'Generating...';
        results.classList.add('hidden');
        errorMsg.classList.add('hidden');

        const formData = new FormData(form);
        
        // Ensure booleans are handled correctly for FastAPI Form
        formData.set('no_auto_align', 'false'); // Example placeholder
        formData.set('snap_screws', currentTab === 'pcb' ? 'true' : 'false');

        try {
            const response = await fetch('/api/generate', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Generation failed');
            }

            // Update UI with metadata
            const meta = data.metadata;
            document.getElementById('stat-keys').textContent = meta.keys;
            document.getElementById('stat-dims').textContent = `${parseFloat(meta.plate_w).toFixed(2)} x ${parseFloat(meta.plate_h).toFixed(2)} mm`;
            document.getElementById('stat-screws').textContent = meta.screws;
            
            const notice = document.getElementById('validation-notice');
            if (meta.issues > 0) {
                notice.textContent = `Warning: ${meta.issues} validation issue(s) detected. Check the console or your design for overlaps.`;
                notice.classList.remove('hidden');
            } else {
                notice.classList.add('hidden');
            }

            // Render SVG preview
            const previewContainer = document.getElementById('preview-container');
            previewContainer.innerHTML = data.svg;

            // Handle file download
            const downloadUrl = `/api/download/${data.dxf_id}`;
            downloadLink.href = downloadUrl;
            downloadLink.onclick = (e) => {
                // let default behavior happen for regular click
            };

            results.classList.remove('hidden');

        } catch (err) {
            errorMsg.textContent = err.message;
            errorMsg.classList.remove('hidden');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Generate DXF';
        }
    });
});
