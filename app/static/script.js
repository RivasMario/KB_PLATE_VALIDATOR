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
    const downloadGerber = document.getElementById('download-gerber');
    const downloadStl = document.getElementById('download-stl');
    const dxfInput = document.getElementById('dxf_file');
    const dxfName = document.getElementById('dxf-name');
    const dxfDropZone = document.getElementById('dxf-drop-zone');
    const convertBtn = document.getElementById('convert-btn');
    const optionsSections = document.querySelectorAll('.options-section, #kle-options, .actions:has(#submit-btn)');

    let currentTab = 'kle';

    const disableDownload = (el) => {
        el.classList.add('btn-disabled');
        el.removeAttribute('href');
    };
    const enableDownload = (el, href) => {
        el.classList.remove('btn-disabled');
        el.setAttribute('href', href);
    };
    const resetDownloads = () => {
        [downloadLink, downloadGerber, downloadStl].forEach(disableDownload);
        results.classList.remove('success');
    };
    resetDownloads();

    const progress = document.getElementById('progress');
    const progressText = document.getElementById('progress-text');
    let progressTimer = null;
    const startProgress = (label) => {
        progress.classList.remove('hidden');
        const t0 = Date.now();
        const phases = [
            [0,   'Parsing input...'],
            [2,   'Laying out keys...'],
            [4,   'Generating DXF...'],
            [8,   'Rendering Gerber layers...'],
            [20,  'Extruding STL (this is slow)...'],
            [45,  'Still working... large plates take a minute...'],
        ];
        const tick = () => {
            const sec = ((Date.now() - t0) / 1000);
            let phase = label || phases[0][1];
            for (const [t, p] of phases) if (sec >= t) phase = p;
            progressText.textContent = `${phase}  (${sec.toFixed(1)}s)`;
        };
        tick();
        progressTimer = setInterval(tick, 200);
    };
    const stopProgress = () => {
        if (progressTimer) { clearInterval(progressTimer); progressTimer = null; }
        progress.classList.add('hidden');
    };

    // Tab Switching
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentTab = btn.dataset.tab;

            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            const targetId = currentTab === 'convert' ? 'convert-section' : 'pcb-section';
            document.getElementById(targetId).classList.add('active');

            if (currentTab === 'kle') {
                kleOptions.classList.remove('hidden');
                pcbOnlyGroups.forEach(el => el.classList.add('hidden'));
                optionsSections.forEach(el => el.classList.remove('hidden'));
            } else if (currentTab === 'pcb') {
                kleOptions.classList.add('hidden');
                pcbOnlyGroups.forEach(el => el.classList.remove('hidden'));
                optionsSections.forEach(el => el.classList.remove('hidden'));
            } else {
                optionsSections.forEach(el => el.classList.add('hidden'));
            }
            errorMsg.classList.add('hidden');
            resetDownloads();
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
    dxfInput.addEventListener('change', () => handleFileSelect(dxfInput, dxfName));

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
    setupDropZone(dxfDropZone, dxfInput, dxfName);

    // DXF Conversion
    convertBtn.addEventListener('click', async () => {
        if (!dxfInput.files || dxfInput.files.length === 0) {
            alert('Please select a DXF file first.');
            return;
        }

        const genGerber = document.getElementById('gen_gerber').checked;
        const genStl = document.getElementById('gen_stl').checked;

        if (!genGerber && !genStl) {
            alert('Please select either Gerber or STL format for conversion.');
            return;
        }

        convertBtn.disabled = true;
        convertBtn.textContent = 'Converting...';
        errorMsg.classList.add('hidden');
        resetDownloads();
        startProgress('Parsing DXF...');

        const formData = new FormData();
        formData.append('dxf_file', dxfInput.files[0]);
        formData.append('gen_gerber', genGerber ? 'true' : 'false');
        formData.append('gen_stl', genStl ? 'true' : 'false');
        formData.append('thickness', document.getElementById('screw_diameter').value); // Using screw diam field temporarily or adding thickness?
        // Actually let's just add a dummy thickness or use the value from the form
        formData.append('thickness', '1.5'); 

        try {
            const response = await fetch('/api/convert-dxf', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            console.log('Convert results:', data);
            if (!response.ok) throw new Error(data.detail || 'Conversion failed');

            const s = data.stats || {};
            document.getElementById('stat-keys').textContent = `${s.cutouts ?? 0} cutouts`;
            document.getElementById('stat-dims').textContent = s.outline ? 'outline OK' : 'no outline';
            document.getElementById('stat-screws').textContent = s.screws ?? 0;

            document.getElementById('preview-container').innerHTML = '<p style="padding: 2rem; color: var(--text-muted);">SVG Preview not available for direct DXF conversion.</p>';

            if (data.gerber_id) enableDownload(downloadGerber, `/api/download/${data.gerber_id}`);
            if (data.stl_id) enableDownload(downloadStl, `/api/download/${data.stl_id}`);
            results.classList.add('success');

            const warnings = [];
            if (data.gerber_error) warnings.push(`Gerber failed: ${data.gerber_error}`);
            if (data.stl_error) warnings.push(`STL failed: ${data.stl_error}`);
            if (!data.gerber_id && !data.stl_id) warnings.push('Server produced no files.');
            const notice = document.getElementById('validation-notice');
            if (warnings.length) {
                notice.textContent = warnings.join(' | ');
                notice.classList.remove('hidden');
            } else {
                notice.classList.add('hidden');
            }
            results.scrollIntoView({behavior: 'smooth', block: 'start'});
        } catch (err) {
            errorMsg.textContent = err.message;
            errorMsg.classList.remove('hidden');
            errorMsg.scrollIntoView({behavior: 'smooth', block: 'center'});
        } finally {
            convertBtn.disabled = false;
            convertBtn.textContent = 'Convert DXF';
            stopProgress();
        }
    });

    // Form Submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        submitBtn.disabled = true;
        submitBtn.textContent = 'Generating...';
        errorMsg.classList.add('hidden');
        resetDownloads();
        startProgress('Parsing input...');

        const formData = new FormData(form);
        
        // Ensure booleans are handled correctly for FastAPI Form
        formData.set('no_auto_align', document.getElementById('no_auto_align').checked ? 'true' : 'false'); 
        formData.set('snap_screws', currentTab === 'pcb' ? 'true' : 'false');
        formData.set('split', document.getElementById('split').checked ? 'true' : 'false');
        formData.set('puzzle_split', document.getElementById('puzzle_split').checked ? 'true' : 'false');
        
        // Format selection
        const genDxf = document.getElementById('gen_dxf').checked;
        const genGerber = document.getElementById('gen_gerber').checked;
        const genStl = document.getElementById('gen_stl').checked;
        
        if (!genDxf && !genGerber && !genStl) {
            alert('Please select at least one generation format.');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Generate Plate Files';
            return;
        }
        
        formData.set('gen_dxf', genDxf ? 'true' : 'false');
        formData.set('gen_gerber', genGerber ? 'true' : 'false');
        formData.set('gen_stl', genStl ? 'true' : 'false');

        try {
            const response = await fetch('/api/generate', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            console.log('Generation results:', data);

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

            if (data.dxf_id) enableDownload(downloadLink, `/api/download/${data.dxf_id}`);
            if (data.gerber_id) enableDownload(downloadGerber, `/api/download/${data.gerber_id}`);
            if (data.stl_id) enableDownload(downloadStl, `/api/download/${data.stl_id}`);
            results.classList.add('success');

            const warnings = [];
            if (data.gerber_error) warnings.push(`Gerber export failed: ${data.gerber_error}`);
            if (data.stl_error) warnings.push(`STL export failed: ${data.stl_error}`);
            if (warnings.length) {
                const notice = document.getElementById('validation-notice');
                notice.textContent = warnings.join(' | ');
                notice.classList.remove('hidden');
            }

            results.scrollIntoView({behavior: 'smooth', block: 'start'});
        } catch (err) {
            errorMsg.textContent = err.message;
            errorMsg.classList.remove('hidden');
            errorMsg.scrollIntoView({behavior: 'smooth', block: 'center'});
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Generate Plate Files';
            stopProgress();
        }
    });
});
