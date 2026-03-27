import React, { useState, useEffect, useCallback } from 'react';
import { Activity, Library, Network, FileDown, Eye, Upload, File, CheckCircle2, Circle, Loader2, Trash2, Play, ExternalLink } from 'lucide-react';
import { format } from 'date-fns';
import { ReactFlow, Controls, Background, MiniMap, useNodesState, useEdgesState } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import './index.css';

// --- CONSTANTS --- //

const PIPELINE_STEPS = [
  { id: 'extract_text', label: 'Extract Text', desc: 'Parsing PDF characters and structure' },
  { id: 'chunking', label: 'Chunking', desc: 'Splitting text into logical decision blocks' },
  { id: 'decision_identification', label: 'Identify Decisions', desc: 'Extracting if/then rules from chunks' },
  { id: 'subtree_building', label: 'Build Subtrees', desc: 'Creating localized logic fragments' },
  { id: 'tree_building', label: 'Merge Tree', desc: 'Assembling master decision graph' },
  { id: 'validation', label: 'Validate', desc: 'Checking for loops and logical consistency' },
  { id: 'json_compilation', label: 'Compile JSON', desc: 'Finalizing canonical guideline format' }
];

// --- VIEW COMPONENTS --- //

const PipelineView = ({ status, tracker, file, onFileChange, onUpload }) => {
  return (
    <div className="main-grid">
      <section className="left-panel">
        <div className="glass-panel card upload-card">
          <h2>Run Pipeline</h2>
          <p className="subtitle">Upload a clinical guideline to start the extraction process.</p>
          <div className="upload-area">
            <input type="file" id="pdf-upload" accept="application/pdf" className="hidden-input" onChange={onFileChange} />
            <label htmlFor="pdf-upload" className="upload-label">
              <Upload className="upload-icon" />
              <span className="upload-text">{file ? `Selected: ${file.name}` : 'Click to browse or drop PDF here'}</span>
            </label>
          </div>
          <button className="btn primary-btn" onClick={onUpload} disabled={!file || status === 'running'}>
            <span>{status === 'running' ? 'Processing...' : 'Start Extraction'}</span>
            {status === 'running' && <Loader2 className="animate-spin w-4 h-4" />}
          </button>
        </div>

        <div className="glass-panel card progress-card">
          <h2>Pipeline Progress</h2>
          <div className="stepper">
            {PIPELINE_STEPS.map((step, idx) => {
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
                    <button className="action-btn" onClick={() => (window.activeOnViewArtifact(a.path, a.step))} title="View Flow">
                      <Network size={16} />
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

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleDelete = async (e, filename) => {
    e.stopPropagation();
    if (confirm(`Delete ${filename}?`)) {
      await onDelete(filename);
      fetchItems();
    }
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

  const fetchPdfs = useCallback(() => {
    fetch('/api/pdfs')
      .then(r => r.json())
      .then(data => { setPdfs(data); setLoading(false); })
      .catch(e => { console.error(e); setLoading(false); });
  }, []);

  useEffect(() => {
    fetchPdfs();
  }, [fetchPdfs]);

  const formatSize = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const handleDelete = async (e, filename) => {
    e.stopPropagation();
    if (confirm(`Remove ${filename} from server?`)) {
      await onDelete(filename);
      fetchPdfs();
    }
  };

  const handleProcess = (e, filename) => {
    e.stopPropagation();
    onProcess(filename);
  };

  return (
    <div className="glass-panel card">
      <h2>PDF Resource Library</h2>
      <p className="subtitle">Source clinical guidelines currently stored on the server.</p>
      {loading ? <div className="loader"></div> : (
        <div className="pdf-grid">
          {pdfs.length === 0 ? <p className="empty-state">No PDFs found.</p> : pdfs.map((pdf, i) => (
            <div key={i} className="glass-panel card pdf-card" onClick={() => window.open(pdf.url, '_blank')}>
              <div className="pdf-header">
                <div className="pdf-icon"><File size={24} /></div>
                <div className="pdf-name" title={pdf.filename}>{pdf.name}</div>
              </div>
              <div className="pdf-meta">
                <span>{formatSize(pdf.size)}</span>
                <span>{format(new Date(pdf.date), 'MMM d, yyyy')}</span>
              </div>
              <div className="card-actions">
                <button className="action-btn process" onClick={(e) => handleProcess(e, pdf.filename)} title="Extract Clinical Tree">
                  <Play size={16} />
                </button>
                <button className="action-btn" onClick={() => window.open(pdf.url, '_blank')} title="View PDF">
                  <ExternalLink size={16} />
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

const TreeViewer = ({ jsonPath }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    if (!jsonPath) return;
    setLoading(true);
    fetch(jsonPath)
      .then(r => r.json())
      .then(d => { 
        setData(d); 
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

        const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(initialNodes, initialEdges);
        setNodes(layoutedNodes);
        setEdges(layoutedEdges);
        setLoading(false);
      })
      .catch(e => { console.error(e); setLoading(false); });
  }, [jsonPath, setNodes, setEdges]);

  if (!jsonPath) return <div className="glass-panel card"><p>No guideline selected. Please upload or select one from the library.</p></div>;
  if (loading) return <div className="glass-panel card"><div className="loader"></div></div>;
  if (!data || !data.nodes) return <div className="glass-panel card"><p>Invalid JSON format or empty tree.</p></div>;

  return (
    <div className="glass-panel card" style={{ height: '70vh', display: 'flex', flexDirection: 'column' }}>
      <h2>Tree Viewer: {data.name || 'Decision Tree'}</h2>
      <div style={{ flexGrow: 1, width: '100%', borderRadius: '12px', overflow: 'hidden', background: 'rgba(0,0,0,0.2)' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          fitView
          attributionPosition="bottom-right"
        >
          <Controls />
          <Background color="#33364f" gap={16} />
          <MiniMap 
            nodeColor="#6366f1"
            maskColor="rgba(0,0,0,0.7)"
            style={{ backgroundColor: '#1e2030' }}
          />
        </ReactFlow>
      </div>
    </div>
  );
};


export default function App() {
  const [activeTab, setActiveTab] = useState('pipeline');
  const [activeJsonPath, setActiveJsonPath] = useState(null);
  
  // Pipeline State (Persisted across tabs)
  const [file, setFile] = useState(null);
  const [pipelineStatus, setPipelineStatus] = useState('idle');
  const [runId, setRunId] = useState(null);
  const [tracker, setTracker] = useState({ current: null, completed: [], artifacts: [] });

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
    setActiveTab('pipeline'); // Switch to pipeline view to see progress
    
    try {
      const res = await fetch(`/api/reprocess/${filename}`, { method: 'POST' });
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
            <Network className="inline w-4 h-4 mr-1"/> View Tree
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
          />
        )}
        {activeTab === 'pdfs' && (
          <PdfLibraryView onProcess={handleReprocess} onDelete={handleDeletePdf} />
        )}
        {activeTab === 'library' && (
          <LibraryView onSelect={handleSelectJson} onDelete={handleDeleteGuideline} />
        )}
        {activeTab === 'view' && (
          <TreeViewer jsonPath={activeJsonPath} />
        )}
      </main>
    </div>
  );
}
