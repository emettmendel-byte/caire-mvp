document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('pdf-upload');
    const runBtn = document.getElementById('run-pipeline-btn');
    const statusText = document.getElementById('system-status-text');
    const statusDot = document.getElementById('system-status-dot');
    
    // Prompts
    const tabsContainer = document.getElementById('prompt-tabs');
    const contentContainer = document.getElementById('prompt-content');
    const savePromptsBtn = document.getElementById('save-prompts-btn');
    
    // Status
    const statusTracker = document.getElementById('status-tracker');
    const artifactsGrid = document.getElementById('artifacts-grid');
    
    // Modal
    const modal = document.getElementById('json-modal');
    const closeModalBtn = document.getElementById('close-modal');
    const jsonOutput = document.getElementById('json-output');
    const modalTitle = document.getElementById('modal-title');
    
    // State
    let selectedFile = null;
    let currentRunId = null;
    let pollInterval = null;
    let promptsData = {};
    let activePromptId = null;
    
    const pipelineSteps = [
        { id: 'extract_text', name: 'Extract Text', desc: 'Parsing PDF and extracting clinical statements' },
        { id: 'chunking', name: 'Chunk Text', desc: 'Grouping statements into logical sub-topics' },
        { id: 'decision_identification', name: 'Identify Decisions', desc: 'Detecting conditionals per chunk' },
        { id: 'subtree_building', name: 'Build Subtrees', desc: 'Drafting logic tree fragments' },
        { id: 'tree_building', name: 'Merge Master Tree', desc: 'Assembling JSON decision tree skeleton' },
        { id: 'validation', name: 'Validate Logic', desc: 'Reviewing against pathways for errors' },
        { id: 'json_compilation', name: 'Compile Final JSON', desc: 'Producing the finalized output artifact' }
    ];

    // Initialization
    init();

    async function init() {
        await fetchPrompts();
        renderStepsTracker([], null);
    }

    // --- Prompts Management ---
    async function fetchPrompts() {
        try {
            const res = await fetch('/api/prompts');
            if (res.ok) {
                promptsData = await res.json();
                renderPromptTabs();
            }
        } catch (e) {
            console.error("Failed to fetch prompts", e);
        }
    }

    function renderPromptTabs() {
        tabsContainer.innerHTML = '';
        contentContainer.innerHTML = '';
        
        const ids = Object.keys(promptsData).sort();
        if (ids.length === 0) return;
        
        if (!activePromptId) activePromptId = ids[0];
        
        ids.forEach(id => {
            const prompt = promptsData[id];
            
            // Tab
            const btn = document.createElement('button');
            btn.className = `tab-btn ${id === activePromptId ? 'active' : ''}`;
            btn.innerText = `Prompt ${id.split('_')[1]}`;
            btn.title = prompt.description;
            btn.onclick = () => switchTab(id);
            tabsContainer.appendChild(btn);
            
            // Editor
            const editorDiv = document.createElement('div');
            editorDiv.className = `prompt-editor`;
            editorDiv.style.display = id === activePromptId ? 'flex' : 'none';
            editorDiv.id = `editor-wrapper-${id}`;
            
            const desc = document.createElement('p');
            desc.className = 'subtitle';
            desc.innerText = prompt.description;
            
            const textarea = document.createElement('textarea');
            textarea.id = `textarea-${id}`;
            textarea.value = prompt.text;
            
            editorDiv.appendChild(desc);
            editorDiv.appendChild(textarea);
            contentContainer.appendChild(editorDiv);
        });
    }
    
    function switchTab(id) {
        activePromptId = id;
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.prompt-editor').forEach(ed => ed.style.display = 'none');
        
        const idx = Object.keys(promptsData).sort().indexOf(id);
        if(idx !== -1) {
            tabsContainer.children[idx].classList.add('active');
        }
        document.getElementById(`editor-wrapper-${id}`).style.display = 'flex';
    }
    
    savePromptsBtn.addEventListener('click', async () => {
        savePromptsBtn.innerText = 'Saving...';
        savePromptsBtn.disabled = true;
        
        try {
            for (const id of Object.keys(promptsData)) {
                const text = document.getElementById(`textarea-${id}`).value;
                if (text !== promptsData[id].text) {
                    await fetch('/api/prompts', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id, text })
                    });
                    promptsData[id].text = text;
                }
            }
            savePromptsBtn.innerText = 'Saved!';
            setTimeout(() => {
                savePromptsBtn.innerText = 'Save Changes';
                savePromptsBtn.disabled = false;
            }, 2000);
        } catch (e) {
            console.error("Failed to save", e);
            savePromptsBtn.innerText = 'Error';
            savePromptsBtn.disabled = false;
        }
    });

    // --- File Upload ---
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'var(--primary-color)';
        dropZone.style.background = 'rgba(99, 102, 241, 0.1)';
    });
    
    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'rgba(255, 255, 255, 0.15)';
        dropZone.style.background = 'rgba(0,0,0,0.2)';
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'rgba(255, 255, 255, 0.15)';
        dropZone.style.background = 'rgba(0,0,0,0.2)';
        
        if (e.dataTransfer.files.length) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFileSelect(e.target.files[0]);
        }
    });
    
    function handleFileSelect(file) {
        if (file.type !== 'application/pdf') {
            alert("Please select a valid PDF file.");
            return;
        }
        selectedFile = file;
        dropZone.querySelector('.upload-text').innerText = `Selected: ${file.name}`;
        runBtn.disabled = false;
    }

    // --- Pipeline Execution ---
    runBtn.addEventListener('click', async () => {
        if (!selectedFile) return;
        
        // Reset UI
        runBtn.disabled = true;
        runBtn.querySelector('span').innerText = 'Starting...';
        runBtn.querySelector('.loader').classList.remove('hidden');
        artifactsGrid.innerHTML = '';
        
        const formData = new FormData();
        formData.append('file', selectedFile);
        
        try {
            const res = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            
            if (res.ok) {
                currentRunId = data.run_id;
                startPolling();
                statusText.innerText = 'Processing Outline';
                statusDot.style.backgroundColor = 'var(--accent-warning)';
                statusDot.style.boxShadow = '0 0 10px var(--accent-warning)';
            } else {
                throw new Error(data.detail);
            }
        } catch (e) {
            console.error("Failed to start", e);
            alert("Failed to start pipeline: " + e.message);
            resetRunBtn();
        }
    });

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        
        pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/status/${currentRunId}`);
                const data = await res.json();
                
                renderStepsTracker(data.completed_steps || [], data.current_step);
                renderArtifacts(data.artifacts || []);
                
                if (data.status === 'completed' || data.status === 'failed') {
                    clearInterval(pollInterval);
                    resetRunBtn();
                    statusText.innerText = data.status === 'completed' ? 'Pipeline Complete' : 'Pipeline Failed';
                    const finalColor = data.status === 'completed' ? 'var(--accent-success)' : 'var(--accent-error)';
                    statusDot.style.backgroundColor = finalColor;
                    statusDot.style.boxShadow = `0 0 10px ${finalColor}`;
                }
            } catch (e) {
                console.error("Poll error", e);
            }
        }, 2000);
    }

    function resetRunBtn() {
        runBtn.disabled = false;
        runBtn.querySelector('span').innerText = 'Run Pipeline';
        runBtn.querySelector('.loader').classList.add('hidden');
    }

    // --- Rendering UI Updates ---
    function renderStepsTracker(completed, current) {
        statusTracker.innerHTML = '';
        
        pipelineSteps.forEach((step, index) => {
            const div = document.createElement('div');
            div.className = 'status-step';
            
            const isCompleted = completed.includes(step.id);
            const isActive = current === step.id;
            
            if (isCompleted) div.classList.add('completed');
            if (isActive) div.classList.add('active');
            
            const iconContent = isCompleted ? '✓' : (index + 1);
            
            div.innerHTML = `
                <div class="step-icon">${iconContent}</div>
                <div class="step-details">
                    <span class="step-title">${step.name}</span>
                    <span class="step-desc">${isActive ? 'Processing...' : step.desc}</span>
                </div>
            `;
            statusTracker.appendChild(div);
            
            // Auto scroll to active step
            if (isActive) {
                div.scrollIntoView({ behavior: "smooth", block: "nearest" });
            }
        });
    }
    
    function renderArtifacts(artifacts) {
        if (artifacts.length === 0) {
            artifactsGrid.innerHTML = '<div class="empty-state">No artifacts generated yet.</div>';
            return;
        }
        
        artifactsGrid.innerHTML = '';
        artifacts.forEach(item => {
            const div = document.createElement('div');
            div.className = 'glass-panel artifact-card';
            div.innerHTML = `
                <div class="artifact-info">
                    <span class="artifact-title">${item.step.replace(/_/g, ' ').toUpperCase()} JSON</span>
                    <span class="artifact-subtitle">${item.summary}</span>
                </div>
                <button class="artifact-action" data-path="${item.path}" data-title="${item.step}">View</button>
            `;
            artifactsGrid.appendChild(div);
        });
        
        // Add click listeners
        document.querySelectorAll('.artifact-action').forEach(btn => {
            btn.addEventListener('click', () => {
                viewJson(btn.getAttribute('data-title'), btn.getAttribute('data-path'));
            });
        });
    }

    async function viewJson(title, path) {
        // Technically since artifacts are in a backend folder not mounted, 
        // wait we need to mount /artifacts statically, or fetch it via a new API endpoint.
        // Let's modify the frontend to fetch the raw file via /artifacts endpoint.
        try {
            const res = await fetch(path);
            const data = await res.json();
            jsonOutput.innerText = JSON.stringify(data, null, 2);
            modalTitle.innerText = `${title.toUpperCase()} Artifact`;
            modal.classList.remove('hidden');
        } catch (e) {
            console.error(e);
            jsonOutput.innerText = "Error loading artifact.";
            modalTitle.innerText = "Error";
            modal.classList.remove('hidden');
        }
    }

    closeModalBtn.addEventListener('click', () => {
        modal.classList.add('hidden');
    });
});
