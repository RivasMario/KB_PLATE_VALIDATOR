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

    let currentTab = 'pcb';

    // Tab Switching
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentTab = btn.dataset.tab;

            if (currentTab === 'kle') {
                kleOptions.classList.remove('hidden');
                pcbOnlyGroups.forEach(el => el.classList.add('hidden'));
                pcbInput.required = false;
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

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || 'Generation failed');
            }

            // Get metadata from headers
            const keys = response.headers.get('X-Keys');
            const width = parseFloat(response.headers.get('X-Plate-Width')).toFixed(2);
            const height = parseFloat(response.headers.get('X-Plate-Height')).toFixed(2);
            const screws = response.headers.get('X-Screws');
            const issues = parseInt(response.headers.get('X-Issues'));

            // Handle file download
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            
            // Auto-trigger download
            const a = document.createElement('a');
            a.href = url;
            a.download = 'plate.dxf';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            // Update UI
            document.getElementById('stat-keys').textContent = keys;
            document.getElementById('stat-dims').textContent = `${width} x ${height} mm`;
            document.getElementById('stat-screws').textContent = screws;
            
            const notice = document.getElementById('validation-notice');
            if (issues > 0) {
                notice.textContent = `Warning: ${issues} validation issue(s) detected. Check the console or your design for overlaps.`;
                notice.classList.remove('hidden');
            } else {
                notice.classList.add('hidden');
            }

            downloadLink.href = url;
            downloadLink.onclick = (e) => {
                e.preventDefault();
                const a2 = document.createElement('a');
                a2.href = url;
                a2.download = 'plate.dxf';
                a2.click();
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
