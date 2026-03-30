import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Activity, Library, Network, FileDown, Eye, Upload, File, CheckCircle2, Circle, Loader2, Trash2, Play, ExternalLink, BookOpen, Plus, Save, X, ChevronDown, Settings2 } from 'lucide-react';
import { format } from 'date-fns';
import { ReactFlow, Controls, Background, MiniMap, useNodesState, useEdgesState } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import './index.css';

// --- CONSTANTS --- //

const PIPELINE_STEPS = [
  { id: 'manual_repair', label: 'Manual Repair', desc: 'Identify gaps/contradictions in audit' },
  { id: 'redteam_audit', label: 'Red-team Audit', desc: 'Hostile check for logic failures' },
  { id: 'repair_drafting', label: 'Draft Repairs', desc: 'Generating verbatim code fixes' },
  { id: 'facts_extraction', label: 'Extract Facts', desc: 'Atomic clinical facts (CSV)' },
  { id: 'symbols_predicates', label: 'Model Data', desc: 'Hungarian symbols & predicates' },
  { id: 'factsheet_builder', label: 'Build Factsheet', desc: 'Compiling factsheet.json tree' },
  { id: 'tree_validation', label: 'Validate Tree', desc: 'Safety and schema audit' },
  { id: 'governance', label: 'Governance', desc: 'Final manifest and deployment audit' }
];

// --- VIEW COMPONENTS --- //

const PipelineView = ({ status, tracker, file, onFileChange, onUpload, onViewArtifact, pipelines, selectedPipelineId, onPipelineChange, promptBank }) => {
  const currentRecipe = pipelines.find(p => p.id === selectedPipelineId);
  const steps = Array.isArray(currentRecipe?.steps) ? currentRecipe.steps : [];

  const dynamicSteps = steps.map((step, idx) => {
    const prompt = promptBank[step.prompt_id];
    return {
      id: step.id || `s${idx}`,
      label: step.name || prompt?.name || `Step ${idx + 1}`,
      desc: prompt?.description || `Executing ${step.name || 'task'}...`
    };
  });

  return (
    <div className="main-grid">
      <section className="left-panel">
        <div className="glass-panel card upload-card">
          <h2>Run Pipeline</h2>
          <p className="subtitle">Upload a clinical guideline to start the extraction process.</p>

          <div className="pipeline-selector">
            <label className="selector-label"><Settings2 size={14}/> Pipeline Configuration</label>
            <select
              className="pipeline-select"
              value={selectedPipelineId}
              onChange={e => onPipelineChange(e.target.value)}
              disabled={status === 'running'}
            >
              {pipelines.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>

          <div className="upload-area">
            <input type="file" id="pdf-upload" accept="application/pdf" className="hidden-input" onChange={onFileChange} />
            <label htmlFor="pdf-upload" className="upload-label">
              <Upload className="upload-icon" />
              <span className="upload-text">{file ? `Selected: ${file.name}` : 'Click to browse or drop PDF here'}</span>
            </label>
          </div>
          <button className="btn primary-btn centered-processing" onClick={onUpload} disabled={!file || status === 'running'}>
            {status === 'running'
              ? (
                <div className="processing-inner">
                  <Loader2 className="animate-spin" size={18} />
                  <span>Processing...</span>
                </div>
              )
              : <span>Start Extraction</span>
            }
          </button>
        </div>

        <div className="glass-panel card progress-card">
          <h2>Pipeline Progress</h2>
          <div className="stepper">
            {dynamicSteps.map((step, idx) => {
              const isCompleted = tracker.completed.includes(step.id);
              const isActive = tracker.current?.includes(step.id);
              return (
                <div key={step.id} className={`step-item ${isCompleted ? 'completed' : ''} ${isActive ? 'active' : ''}`}>
                  <div className="step-indicator">
                    {isCompleted ? <CheckCircle2 size={18} /> : (isActive ? <Loader2 size={18} className="animate-spin" /> : <span>{idx + 1}</span>)}
                  </div>
                  <div className="step-content">
                    <span className="step-label">{step.label}</span>
                    <span className="step-description">{step.desc}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>
      
      <section className="right-panel">
        <div className="glass-panel card status-card">
          <h2>Generation Artifacts</h2>
          <div className="artifacts-grid">
            {tracker.artifacts.length === 0 ? (
              <div className="empty-state">Artifacts will appear here as they are generated.</div>
            ) : (
              tracker.artifacts.map((a, i) => (
                <div key={i} className="glass-panel artifact-card">
                  <div className="artifact-info">
                    <span className="artifact-title">{a.step.toUpperCase().replace('_', ' ')}</span>
                    <span className="artifact-subtitle">{a.summary}</span>
                  </div>
                  <div className="card-actions">
                    <button className="action-btn" onClick={() => (window.activeOnViewArtifact(a.path, a.step))} title="View Content">
                      {a.path.endsWith('.json') ? <Network size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </section>
    </div>
  );
};

const LibraryView = ({ onSelect, onDelete }) => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchItems = useCallback(() => {
    fetch('/api/library')
      .then(r => r.json())
      .then(data => { setItems(data); setLoading(false); })
      .catch(e => { console.error(e); setLoading(false); });
  }, []);

  useEffect(() => { fetchItems(); }, [fetchItems]);

  const handleDelete = async (e, filename) => {
    e.stopPropagation();
    if (confirm(`Delete ${filename}?`)) { await onDelete(filename); fetchItems(); }
  };

  return (
    <div className="glass-panel card">
      <h2>Guideline Library</h2>
      <p className="subtitle">Previously processed clinical guidelines ready for viewing.</p>
      {loading ? <div className="loader"></div> : (
        <div className="library-grid">
          {items.length === 0 ? <p className="empty-state">No guidelines found.</p> : items.map((item, i) => (
            <div key={i} className="glass-panel artifact-card library-card" onClick={() => onSelect(item.path)}>
              <div className="flow-node-title">{item.name}</div>
              <div className="library-meta">
                <span>{item.id}</span>
                <span>{format(new Date(item.date), 'MMM d, yyyy HH:mm')}</span>
              </div>
              <div className="card-actions">
                <button className="action-btn delete" onClick={(e) => handleDelete(e, item.filename)} title="Delete Guideline">
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const PdfLibraryView = ({ onProcess, onDelete }) => {
  const [pdfs, setPdfs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [viewingPdf, setViewingPdf] = useState(null);

  const fetchPdfs = useCallback(() => {
    fetch('/api/pdfs')
      .then(r => r.json())
      .then(data => { setPdfs(data); setLoading(false); })
      .catch(e => { console.error(e); setLoading(false); });
  }, []);

  useEffect(() => { fetchPdfs(); }, [fetchPdfs]);

  const formatSize = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const handleDelete = async (e, filename) => {
    e.stopPropagation();
    if (confirm(`Remove ${filename} from server?`)) { await onDelete(filename); fetchPdfs(); if (viewingPdf === filename) setViewingPdf(null); }
  };

  const handleView = (url) => { if (viewingPdf === url) setViewingPdf(null); else setViewingPdf(url); };

  return (
    <div className={`pdf-library-layout ${viewingPdf ? 'with-viewer' : ''}`}>
      <div className="glass-panel card pdf-list-panel">
        <div className="card-header-row">
          <div>
            <h2>PDF Resource Library</h2>
            <p className="subtitle">Source clinical guidelines currently stored on the server.</p>
          </div>
        </div>
        
        {loading ? <div className="loader"></div> : (
          <div className="pdf-grid">
            {pdfs.length === 0 ? <p className="empty-state">No PDFs found.</p> : pdfs.map((pdf, i) => (
              <div key={i} className={`glass-panel card pdf-card ${viewingPdf === pdf.url ? 'active' : ''}`} onClick={() => handleView(pdf.url)}>
                <div className="pdf-header">
                  <div className="pdf-icon"><File size={24} /></div>
                  <div className="pdf-name" title={pdf.filename}>{pdf.name}</div>
                </div>
                <div className="pdf-meta">
                  <span>{formatSize(pdf.size)}</span>
                  <span>{format(new Date(pdf.date), 'MMM d, yyyy')}</span>
                </div>
                <div className="card-actions">
                  <button className="action-btn process" onClick={(e) => { e.stopPropagation(); onProcess(pdf.filename); }} title="Extract Clinical Tree">
                    <Play size={16} />
                  </button>
                  <button className="action-btn" onClick={(e) => { e.stopPropagation(); handleView(pdf.url); }} title="View Sidebar">
                    <Eye size={16} />
                  </button>
                  <button className="action-btn delete" onClick={(e) => handleDelete(e, pdf.filename)} title="Delete Source">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {viewingPdf && (
        <div className="glass-panel card pdf-viewer-sidebar">
          <div className="viewer-header">
            <h3>PDF Preview</h3>
            <button className="icon-btn" onClick={() => setViewingPdf(null)}><X size={18}/></button>
          </div>
          <iframe src={viewingPdf} className="pdf-frame" title="PDF Viewer" />
        </div>
      )}
    </div>
  );
};

// --- DAGRE LAYOUT HELPER --- //
const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

const getLayoutedElements = (nodes, edges, direction = 'TB') => {
  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 300, height: 100 });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  nodes.forEach((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    node.targetPosition = 'top';
    node.sourcePosition = 'bottom';
    node.position = {
      x: nodeWithPosition.x - 300 / 2,
      y: nodeWithPosition.y - 100 / 2,
    };
    return node;
  });

  return { nodes, edges };
};

const FileViewer = ({ filePath }) => {
  const [data, setData] = useState(null);
  const [rawText, setRawText] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fileType, setFileType] = useState(null);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    if (!filePath) return;
    setLoading(true);
    setData(null); setRawText(null);

    const ext = filePath.split('.').pop().toLowerCase();
    setFileType(ext);

    if (ext === 'json') {
      fetch(filePath)
        .then(r => r.json())
        .then(d => {
          setData(d);
          setRawText(JSON.stringify(d, null, 2));
          const initialNodes = (d.nodes || []).map((n) => ({
            id: n.id,
            type: 'default',
            position: { x: 0, y: 0 },
            style: { background: 'transparent', border: 'none', padding: 0, width: 300 },
            data: {
              label: (
                <div className="flow-node" style={{ margin: 0 }}>
                  <div className="flow-node-header">
                    <span className="flow-node-title">{n.label || n.id}</span>
                    <span className="flow-node-badge">{n.type}</span>
                  </div>
                  <div className="flow-node-body" style={{fontSize: '0.8rem', marginTop:'0.5rem', paddingTop:'0.5rem'}}>
                    {n.description}
                  </div>
                </div>
              )
            }
          }));
          const initialEdges = (d.edges || []).map((e) => ({
            id: `${e.source_id}-${e.target_id}`,
            source: e.source_id,
            target: e.target_id,
            label: e.label,
            animated: true,
            style: { stroke: '#6366f1', strokeWidth: 2 }
          }));
          const { nodes: ln, edges: le } = getLayoutedElements(initialNodes, initialEdges);
          setNodes(ln); setEdges(le);
          setLoading(false);
        })
        .catch(e => { console.error(e); setLoading(false); });
    } else {
      fetch(filePath)
        .then(r => r.text())
        .then(t => { setRawText(t); setLoading(false); })
        .catch(e => { console.error(e); setLoading(false); });
    }
  }, [filePath, setNodes, setEdges]);

  if (!filePath) return <div className="glass-panel card"><p>No file selected. Upload a guideline or click an artifact to view it.</p></div>;
  if (loading) return <div className="glass-panel card"><div className="loader"></div></div>;

  if (fileType === 'json') {
    const hasTree = data && data.nodes && data.nodes.length > 0;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        <div className="glass-panel view-breadcrumb">
          <BookOpen size={14} className="opacity-60" />
          <span>Viewing {filePath.split('/').pop()}</span>
        </div>
        {hasTree ? (
          <div className="glass-panel card" style={{ height: '65vh', display: 'flex', flexDirection: 'column' }}>
            <h2>Decision Tree: {data.name || 'File'}</h2>
            <div style={{ flexGrow: 1, borderRadius: '12px', overflow: 'hidden', background: 'rgba(0,0,0,0.2)' }}>
              <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} fitView attributionPosition="bottom-right">
                <Controls />
                <Background color="#33364f" gap={16} />
                <MiniMap nodeColor="#6366f1" maskColor="rgba(0,0,0,0.7)" style={{ backgroundColor: '#1e2030' }} />
              </ReactFlow>
            </div>
          </div>
        ) : (
          <div className="glass-panel card"><p style={{ color: 'var(--text-secondary)' }}>No renderable decision tree in this JSON (no nodes/edges).</p></div>
        )}
        <div className="glass-panel card">
          <h2 style={{ marginBottom: '0.75rem' }}>Raw JSON</h2>
          <pre className="raw-file-content">{rawText}</pre>
        </div>
      </div>
    );
  }

  // MD / CSV / plain text
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      <div className="glass-panel view-breadcrumb">
        <BookOpen size={14} className="opacity-60" />
        <span>Viewing {filePath.split('/').pop()}</span>
      </div>
      <div className="glass-panel card">
        <h2 style={{ marginBottom: '0.75rem' }}>{filePath.split('/').pop()}</h2>
        <pre className="raw-file-content">{rawText || 'Empty file.'}</pre>
      </div>
    </div>
  );
};


const PipelineBuilderView = ({ promptBank, pipelines, onRefresh }) => {
  const [editingPrompt, setEditingPrompt] = useState(null);
  const [newPrompt, setNewPrompt] = useState({ id: '', name: '', text: '' });
  const [showNew, setShowNew] = useState(false);
  const [editingPipeline, setEditingPipeline] = useState(null);
  const [newPipelineSteps, setNewPipelineSteps] = useState([]); // Array of steps
  const [newPipelineMeta, setNewPipelineMeta] = useState({ id: '', name: '', description: '' });
  const [showNewPipeline, setShowNewPipeline] = useState(false);
  const [activeSection, setActiveSection] = useState('pipelines');

  const promptList = Object.values(promptBank);

  const savePrompt = async (prompt) => {
    await fetch('/api/prompt-bank', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(prompt)
    });
    onRefresh();
    setShowNew(false);
    setEditingPrompt(null);
  };

  const deletePrompt = async (id) => {
    if (!confirm(`Delete prompt "${id}"?`)) return;
    await fetch(`/api/prompt-bank/${id}`, { method: 'DELETE' });
    onRefresh();
  };

  const savePipeline = async () => {
    const recipe = { ...newPipelineMeta, steps: newPipelineSteps };
    await fetch('/api/pipelines', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(recipe)
    });
    onRefresh();
    setShowNewPipeline(false);
  };

  const deletePipeline = async (id) => {
    if (!confirm(`Delete pipeline "${id}"?`)) return;
    await fetch(`/api/pipelines/${id}`, { method: 'DELETE' });
    onRefresh();
  };

  const startEditPipeline = (pipeline) => {
    setNewPipelineMeta({ id: pipeline.id, name: pipeline.name, description: pipeline.description || '' });
    setNewPipelineSteps(Array.isArray(pipeline.steps) ? [...pipeline.steps] : []);
    setShowNewPipeline(true);
    setEditingPipeline(pipeline.id);
  };

  const addStep = () => {
    const newStep = { id: `s${newPipelineSteps.length + 1}`, name: 'New Task', prompt_id: '' };
    setNewPipelineSteps([...newPipelineSteps, newStep]);
  };

  const removeStep = (idx) => {
    const updated = [...newPipelineSteps];
    updated.splice(idx, 1);
    setNewPipelineSteps(updated);
  };

  const moveStep = (idx, direction) => {
    if (idx + direction < 0 || idx + direction >= newPipelineSteps.length) return;
    const updated = [...newPipelineSteps];
    const item = updated[idx];
    updated.splice(idx, 1);
    updated.splice(idx + direction, 0, item);
    setNewPipelineSteps(updated);
  };

  return (
    <div className="builder-layout">
      <div className="builder-header">
        <div className="tab-group">
          <button className={`tab-btn ${activeSection === 'pipelines' ? 'active' : ''}`} onClick={() => setActiveSection('pipelines')}>Pipeline Recipes</button>
          <button className={`tab-btn ${activeSection === 'prompts' ? 'active' : ''}`} onClick={() => setActiveSection('prompts')}>Prompt Bank</button>
        </div>
        {activeSection === 'pipelines' && !showNewPipeline && (
          <button className="btn primary-btn small" onClick={() => {
            setNewPipelineMeta({ id: '', name: '', description: '' });
            setNewPipelineSteps([]);
            setEditingPipeline(null);
            setShowNewPipeline(true);
          }}><Plus size={14}/> New Pipeline</button>
        )}
        {activeSection === 'prompts' && !showNew && (
          <button className="btn primary-btn small" onClick={() => {
            setNewPrompt({ id: '', name: '', text: '' });
            setEditingPrompt(null);
            setShowNew(true);
          }}><Plus size={14}/> Create Prompt</button>
        )}
      </div>

      <div className="builder-main">
        {activeSection === 'pipelines' && (
          <div className="glass-panel card">
            {showNewPipeline ? (
              <div className="pipeline-workspace">
                <div className="workspace-header">
                  <h3>{editingPipeline ? 'Refining Pipeline' : 'Designing New Pipeline'}</h3>
                  <div className="header-actions">
                    <button className="btn primary-btn small" onClick={savePipeline} disabled={!newPipelineMeta.id}><Save size={14}/> Save</button>
                    <button className="btn ghost-btn small" onClick={() => setShowNewPipeline(false)}><X size={14}/></button>
                  </div>
                </div>
                <div className="meta-inputs">
                  <input className="form-input" placeholder="Pipeline ID (slug)" value={newPipelineMeta.id} onChange={e => setNewPipelineMeta(p => ({...p, id: e.target.value}))} disabled={!!editingPipeline} />
                  <input className="form-input" placeholder="Display Name" value={newPipelineMeta.name} onChange={e => setNewPipelineMeta(p => ({...p, name: e.target.value}))} />
                </div>
                
                <div className="timeline-builder">
                  {newPipelineSteps.map((step, idx) => (
                    <div key={idx} className="timeline-item">
                      <div className="item-number">{idx + 1}</div>
                      <div className="item-controls">
                        <input className="step-name-input" value={step.name} onChange={e => {
                          const updated = [...newPipelineSteps];
                          updated[idx].name = e.target.value;
                          setNewPipelineSteps(updated);
                        }} placeholder="Step Name..." />
                        <select className="step-prompt-select" value={step.prompt_id} onChange={e => {
                          const updated = [...newPipelineSteps];
                          updated[idx].prompt_id = e.target.value;
                          setNewPipelineSteps(updated);
                        }}>
                          <option value="">Select Prompt Template...</option>
                          {promptList.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                        </select>
                      </div>
                      <div className="item-actions">
                        <button className="icon-btn" onClick={() => moveStep(idx, -1)}><ChevronUp size={14}/></button>
                        <button className="icon-btn" onClick={() => moveStep(idx, 1)}><ChevronDown size={14}/></button>
                        <button className="icon-btn delete" onClick={() => removeStep(idx)}><Trash2 size={14}/></button>
                      </div>
                    </div>
                  ))}
                  <button className="add-step-btn" onClick={addStep}><Plus size={16}/> Add Agent Pipeline Step</button>
                </div>
              </div>
            ) : (
              <div className="recipe-grid">
                {pipelines.length === 0 && <p className="empty-state">No pipelines configured.</p>}
                {pipelines.map(pl => (
                  <div key={pl.id} className="glass-panel recipe-card" onClick={() => startEditPipeline(pl)}>
                    <div className="card-header-row">
                      <div>
                        <h4 className="recipe-title">{pl.name}</h4>
                        <span className="tiny-id">{pl.id}</span>
                      </div>
                      <button className="icon-btn delete" onClick={(e) => { e.stopPropagation(); deletePipeline(pl.id); }}><Trash2 size={14}/></button>
                    </div>
                    <div className="step-count-badge">{(pl.steps || []).length} Agents</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeSection === 'prompts' && (
          <div className="glass-panel card">
            {showNew && (
              <div className="glass-panel prompt-editor">
                <h3>{editingPrompt ? 'Edit Logic Template' : 'Create Logic Template'}</h3>
                <input className="form-input" placeholder="Template ID" value={newPrompt.id} onChange={e => setNewPrompt(p => ({...p, id: e.target.value}))} disabled={!!editingPrompt} />
                <input className="form-input" placeholder="Display Name" value={newPrompt.name} onChange={e => setNewPrompt(p => ({...p, name: e.target.value}))} />
                <textarea className="form-textarea" placeholder="System instructions..." value={newPrompt.text} onChange={e => setNewPrompt(p => ({...p, text: e.target.value}))} rows={10} />
                <div className="editor-actions">
                  <button className="btn primary-btn small" onClick={() => savePrompt(newPrompt)}><Save size={14}/> Save</button>
                  <button className="btn ghost-btn small" onClick={() => setShowNew(false)}><X size={14}/> Cancel</button>
                </div>
              </div>
            )}
            <div className="prompt-grid">
              {promptList.map(p => (
                <div key={p.id} className="glass-panel prompt-item">
                  <div className="prompt-item-header">
                    <div>
                      <span className="prompt-name">{p.name}</span>
                      <span className="tiny-id">{p.id}</span>
                    </div>
                    <div className="card-actions">
                      <button className="action-btn" title="Edit" onClick={() => {
                        setNewPrompt({ id: p.id, name: p.name, text: p.text });
                        setEditingPrompt(p.id);
                        setShowNew(true);
                      }}><Settings2 size={15}/></button>
                      <button className="action-btn delete" title="Delete" onClick={() => deletePrompt(p.id)}><Trash2 size={15}/></button>
                    </div>
                  </div>
                  <pre className="prompt-preview">{p.text.slice(0, 150)}{p.text.length > 150 ? '...' : ''}</pre>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};


export default function App() {
  const [activeTab, setActiveTab] = useState('pipeline');
  const [activeJsonPath, setActiveJsonPath] = useState(null);
  const [selectedPipelineId, setSelectedPipelineId] = useState('default-governance');
  const [pipelines, setPipelines] = useState([{ id: 'default-governance', name: 'Clinical Governance Standard' }]);
  const [promptBank, setPromptBank] = useState({});

  // Pipeline State (Persisted across tabs)
  const [file, setFile] = useState(null);
  const [pipelineStatus, setPipelineStatus] = useState('idle');
  const [runId, setRunId] = useState(null);
  const [tracker, setTracker] = useState({ current: null, completed: [], artifacts: [] });

  const fetchAll = useCallback(() => {
    fetch('/api/pipelines').then(r => r.json()).then(d => { if (d.length) setPipelines(d); }).catch(() => {});
    fetch('/api/prompt-bank').then(r => r.json()).then(d => { setPromptBank(d); }).catch(() => {});
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleSelectJson = (path) => {
    setActiveJsonPath(path);
    setActiveTab('view');
  };

  // Exposed globally so PipelineView can trigger it
  window.activeOnViewArtifact = handleSelectJson;

  const handleFileChange = (e) => {
    if (e.target.files.length) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setPipelineStatus('running');
    setTracker({ current: 'uploading', completed: [], artifacts: [] });
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('pipeline_id', selectedPipelineId);
    
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: formData });
      if (!res.ok) throw new Error('Upload failed');
      const data = await res.json();
      setRunId(data.run_id);
    } catch (err) {
      setPipelineStatus('error');
      console.error(err);
    }
  };

  const handleReprocess = async (filename) => {
    setPipelineStatus('running');
    setTracker({ current: 'initializing', completed: [], artifacts: [] });
    setActiveTab('pipeline');
    try {
      const res = await fetch(`/api/reprocess/${filename}?pipeline_id=${selectedPipelineId}`, { method: 'POST' });
      const data = await res.json();
      setRunId(data.run_id);
    } catch (err) {
      setPipelineStatus('error');
      console.error(err);
    }
  };

  const handleDeleteGuideline = async (filename) => {
    try {
      await fetch(`/api/library/${filename}`, { method: 'DELETE' });
    } catch (e) { console.error(e); }
  };

  const handleDeletePdf = async (filename) => {
    try {
      await fetch(`/api/pdfs/${filename}`, { method: 'DELETE' });
    } catch (e) { console.error(e); }
  };

  // Pipeline Polling Effect (persists across tabs)
  useEffect(() => {
    if (!runId || pipelineStatus !== 'running') return;
    
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/status/${runId}`);
        const data = await res.json();
        
        setTracker({
          current: data.current_step,
          completed: data.completed_steps || [],
          artifacts: data.artifacts || []
        });
        
        if (data.status === 'completed' || data.status === 'failed') {
          setPipelineStatus(data.status);
          clearInterval(interval);
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 2000);
    
    return () => clearInterval(interval);
  }, [runId, pipelineStatus]);

  return (
    <div className="app-container">
      <header className="glass-panel header">
        <div className="logo">
          <span className="logo-icon">✨</span>
          <h1>Caire Medical Guideline Parser</h1>
        </div>
        <div className="header-tabs">
          <button className={`header-tab ${activeTab === 'pipeline' ? 'active' : ''}`} onClick={() => setActiveTab('pipeline')}>
            <Activity className="inline w-4 h-4 mr-1"/> Pipeline
          </button>
          <button className={`header-tab ${activeTab === 'pdfs' ? 'active' : ''}`} onClick={() => setActiveTab('pdfs')}>
            <File className="inline w-4 h-4 mr-1"/> PDFs
          </button>
          <button className={`header-tab ${activeTab === 'library' ? 'active' : ''}`} onClick={() => setActiveTab('library')}>
            <Library className="inline w-4 h-4 mr-1"/> Guidelines
          </button>
          <button className={`header-tab ${activeTab === 'view' ? 'active' : ''}`} onClick={() => setActiveTab('view')}>
            <Network className="inline w-4 h-4 mr-1"/> View
          </button>
          <button className={`header-tab ${activeTab === 'prompts' ? 'active' : ''}`} onClick={() => setActiveTab('prompts')}>
            <BookOpen className="inline w-4 h-4 mr-1"/> Prompts
          </button>
        </div>
        <div className="status-indicator">
          <div className="dot"></div>
          <span>System {pipelineStatus === 'running' ? 'Processing' : 'Ready'}</span>
        </div>
      </header>

      <main>
        {activeTab === 'pipeline' && (
          <PipelineView 
            status={pipelineStatus} 
            tracker={tracker} 
            file={file} 
            onFileChange={handleFileChange} 
            onUpload={handleUpload} 
            onViewArtifact={handleSelectJson}
            pipelines={pipelines}
            selectedPipelineId={selectedPipelineId}
            onPipelineChange={setSelectedPipelineId}
            promptBank={promptBank}
          />
        )}
        {activeTab === 'pdfs' && (
          <PdfLibraryView onProcess={handleReprocess} onDelete={handleDeletePdf} />
        )}
        {activeTab === 'library' && (
          <LibraryView onSelect={handleSelectJson} onDelete={handleDeleteGuideline} />
        )}
        {activeTab === 'prompts' && (
          <PipelineBuilderView 
            promptBank={promptBank} 
            pipelines={pipelines} 
            onRefresh={fetchAll} 
          />
        )}
        {activeTab === 'view' && (
          <FileViewer filePath={activeJsonPath} />
        )}
      </main>
    </div>
  );
}
