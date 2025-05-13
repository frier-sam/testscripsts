pip install dramatiq[sqlite] apscheduler


# utils/background.py
import os
import json
import time
import uuid
import sqlite3
import threading
import dramatiq
from dramatiq.brokers.sqlite import SQLiteBroker
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from apscheduler.schedulers.background import BackgroundScheduler

# Create a SQLite broker for dramatiq
broker_path = os.path.abspath("worker.db")
broker = SQLiteBroker(path=broker_path)
dramatiq.set_broker(broker)

# Database path for storing job information
DB_PATH = os.path.abspath("jobs.db")

# Initialize database
def init_db():
    """Initialize the jobs database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create jobs table for tracking jobs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        params TEXT,
        result TEXT,
        error TEXT
    )
    ''')
    
    conn.commit()
    conn.close()

# Initialize the database on module import
init_db()

# Job status constants
class JobStatus:
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

def get_db_connection():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_job(job_type: str, params: Dict[str, Any]) -> str:
    """
    Create a new job and add it to the queue.
    
    Args:
        job_type: Type of job (e.g., 'explanation', 'comparison')
        params: Job parameters
        
    Returns:
        Job ID
    """
    job_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO jobs (id, type, status, created_at, updated_at, params) VALUES (?, ?, ?, ?, ?, ?)',
        (job_id, job_type, JobStatus.QUEUED, now, now, json.dumps(params))
    )
    conn.commit()
    conn.close()
    
    # Enqueue the job
    process_job.send(job_id)
    
    return job_id

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get job information by ID.
    
    Args:
        job_id: Job ID
        
    Returns:
        Job information or None if not found
    """
    conn = get_db_connection()
    job = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    
    if not job:
        return None
    
    job_dict = dict(job)
    
    # Parse JSON fields
    for field in ['params', 'result']:
        if job_dict.get(field):
            try:
                job_dict[field] = json.loads(job_dict[field])
            except:
                pass  # Keep as string if JSON parsing fails
    
    return job_dict

def update_job_status(job_id: str, status: str, result: Any = None, error: str = None) -> bool:
    """
    Update job status.
    
    Args:
        job_id: Job ID
        status: New status
        result: Job result (if completed)
        error: Error message (if failed)
        
    Returns:
        Success flag
    """
    now = datetime.now().isoformat()
    
    conn = get_db_connection()
    
    try:
        if result is not None:
            # Convert result to JSON string
            result_json = json.dumps(result)
            conn.execute(
                'UPDATE jobs SET status = ?, updated_at = ?, result = ? WHERE id = ?',
                (status, now, result_json, job_id)
            )
        elif error is not None:
            conn.execute(
                'UPDATE jobs SET status = ?, updated_at = ?, error = ? WHERE id = ?',
                (status, now, error, job_id)
            )
        else:
            conn.execute(
                'UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?',
                (status, now, job_id)
            )
            
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating job {job_id}: {e}")
        return False
    finally:
        conn.close()

def get_queue_position(job_id: str) -> int:
    """
    Get the position of a job in the queue.
    
    Args:
        job_id: Job ID
        
    Returns:
        Queue position (1-based) or 0 if not in queue
    """
    conn = get_db_connection()
    
    # Get jobs that are currently queued, ordered by creation time
    queued_jobs = conn.execute(
        'SELECT id FROM jobs WHERE status = ? ORDER BY created_at ASC',
        (JobStatus.QUEUED,)
    ).fetchall()
    
    conn.close()
    
    # Find the position of the job in the queue
    for i, job in enumerate(queued_jobs):
        if job['id'] == job_id:
            return i + 1  # 1-based position
    
    # Job is not in the queue
    return 0

def get_job_count() -> Tuple[int, int, int, int]:
    """
    Get counts of jobs by status.
    
    Returns:
        Tuple of (queued, processing, completed, failed)
    """
    conn = get_db_connection()
    
    queued = conn.execute('SELECT COUNT(*) FROM jobs WHERE status = ?', 
                        (JobStatus.QUEUED,)).fetchone()[0]
    processing = conn.execute('SELECT COUNT(*) FROM jobs WHERE status = ?', 
                            (JobStatus.PROCESSING,)).fetchone()[0]
    completed = conn.execute('SELECT COUNT(*) FROM jobs WHERE status = ?', 
                           (JobStatus.COMPLETED,)).fetchone()[0]
    failed = conn.execute('SELECT COUNT(*) FROM jobs WHERE status = ?', 
                        (JobStatus.FAILED,)).fetchone()[0]
    
    conn.close()
    
    return (queued, processing, completed, failed)

def cleanup_old_jobs(days: int = 7) -> int:
    """
    Clean up old completed and failed jobs.
    
    Args:
        days: Number of days to keep jobs
        
    Returns:
        Number of jobs cleaned up
    """
    cutoff_date = (datetime.now() - datetime.timedelta(days=days)).isoformat()
    
    conn = get_db_connection()
    
    # Get count of jobs to be deleted
    count = conn.execute(
        'SELECT COUNT(*) FROM jobs WHERE status IN (?, ?) AND updated_at < ?',
        (JobStatus.COMPLETED, JobStatus.FAILED, cutoff_date)
    ).fetchone()[0]
    
    # Delete old jobs
    conn.execute(
        'DELETE FROM jobs WHERE status IN (?, ?) AND updated_at < ?',
        (JobStatus.COMPLETED, JobStatus.FAILED, cutoff_date)
    )
    
    conn.commit()
    conn.close()
    
    return count

@dramatiq.actor(max_retries=3, time_limit=300000)  # 5 minute time limit
def process_job(job_id: str):
    """
    Process a job. This is the main worker function that executes the job.
    
    Args:
        job_id: Job ID
    """
    job = get_job(job_id)
    
    if not job:
        print(f"Job {job_id} not found")
        return
    
    # Update job status to processing
    update_job_status(job_id, JobStatus.PROCESSING)
    
    try:
        job_type = job['type']
        params = job['params']
        
        result = None
        
        # Execute different job types
        if job_type == 'explanation':
            result = process_explanation_job(params)
        elif job_type == 'comparison':
            result = process_comparison_job(params)
        else:
            raise ValueError(f"Unknown job type: {job_type}")
        
        # Update job as completed
        update_job_status(job_id, JobStatus.COMPLETED, result)
        
    except Exception as e:
        # Update job as failed
        error_msg = str(e)
        print(f"Error processing job {job_id}: {error_msg}")
        update_job_status(job_id, JobStatus.FAILED, error=error_msg)

def process_explanation_job(params):
    """Process an explanation job."""
    from utils.retrieval import (
        search_index, query_llm, format_results, load_index
    )
    import config
    
    index_dir = params.get('index_dir')
    query_text = params.get('query')
    
    # Load the index
    index_path = os.path.join(config.INDEXES_DIR, index_dir)
    index, tokenized_corpus, corpus, metadata = load_index(index_path)
    
    # Determine if this is likely a variable query
    is_variable_query = 'variable' in query_text.lower() or any(
        keyword in query_text.lower() for keyword in 
        ['var ', 'what is ', 'what\'s ', 'define ', 'explain ', 'purpose of ']
    )
    
    # Search the index
    search_results = search_index(
        query_text, 
        index, 
        tokenized_corpus, 
        corpus, 
        top_k=config.MAX_CHUNKS,
        is_variable_query=is_variable_query
    )
    
    # Prepare context for the LLM
    context = "\n\n".join([
        f"File: {res['document']['path']} (Chunk {res['document']['chunk_id']})\n"
        f"{res['document']['content']}" 
        for res in search_results
    ])
    
    # Get conversation context
    conversation_context = params.get('conversation_context', "")
    
    # Query the LLM
    llm_response = query_llm(
        query_text, 
        context,
        search_results,
        config.VLLM_ENDPOINT, 
        config.VLLM_MODEL,
        conversation_context
    )
    
    # Format the results
    return format_results(search_results, llm_response)

def process_comparison_job(params):
    """Process a comparison job."""
    from utils.retrieval import (
        search_variable_context, compare_implementations, 
        format_sources, load_index
    )
    import config
    
    index1_dir = params.get('index1_dir')
    index2_dir = params.get('index2_dir')
    variable1 = params.get('variable1')
    variable2 = params.get('variable2')
    
    # Load both indexes
    index1_path = os.path.join(config.INDEXES_DIR, index1_dir)
    index2_path = os.path.join(config.INDEXES_DIR, index2_dir)
    
    index1, tokenized_corpus1, corpus1, metadata1 = load_index(index1_path)
    index2, tokenized_corpus2, corpus2, metadata2 = load_index(index2_path)
    
    # Search for variables in respective indexes
    results1 = search_variable_context(variable1, index1, tokenized_corpus1, corpus1)
    results2 = search_variable_context(variable2, index2, tokenized_corpus2, corpus2)
    
    # Prepare context for the LLM
    context1 = "\n\n".join([
        f"File: {res['document']['path']} (Chunk {res['document']['chunk_id']})\n"
        f"{res['document']['content']}" 
        for res in results1
    ])
    
    context2 = "\n\n".join([
        f"File: {res['document']['path']} (Chunk {res['document']['chunk_id']})\n"
        f"{res['document']['content']}" 
        for res in results2
    ])
    
    # Query the LLM to compare the implementations
    comparison = compare_implementations(
        variable1, variable2,
        context1, context2,
        metadata1, metadata2,
        results1, results2,
        config.VLLM_ENDPOINT,
        config.VLLM_MODEL
    )
    
    # Format the results
    return {
        "comparison": comparison["generated_text"],
        "sources1": format_sources(results1, metadata1['language']),
        "sources2": format_sources(results2, metadata2['language']),
        "variable1": variable1,
        "variable2": variable2,
        "language1": metadata1['language'],
        "language2": metadata2['language'],
        "repo1": metadata1['name'],
        "repo2": metadata2['name']
    }

# Start a cleanup scheduler to remove old jobs
scheduler = BackgroundScheduler()
scheduler.add_job(lambda: cleanup_old_jobs(7), 'interval', days=1)
scheduler.start()

# Start worker process(es)
def start_workers(num_workers=2):
    """Start background worker processes."""
    from dramatiq.cli import main as dramatiq_main
    import sys
    
    # Create worker processes
    for i in range(num_workers):
        worker_thread = threading.Thread(
            target=lambda: dramatiq_main(
                [
                    "dramatiq", 
                    "utils.background",
                    "--processes", "1",
                    "--threads", "2"
                ]
            ),
            daemon=True
        )
        worker_thread.start()
        print(f"Started worker {i+1}")



# Add to app.py

# Import worker functionality
from utils.background import (
    create_job, get_job, get_queue_position, 
    JobStatus, start_workers
)

# Start background workers
start_workers(num_workers=2)

@app.route('/api/query-async/<index_dir>', methods=['POST'])
def query_async(index_dir):
    """API endpoint for queuing an asynchronous query request"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Get the query from the request
    data = request.json
    query_text = data.get('query')
    conversation_id = data.get('conversation_id')
    
    if not query_text:
        return jsonify({'error': 'No query provided'}), 400
    
    # Load the index
    index_path = os.path.join(config.INDEXES_DIR, index_dir)
    
    if not os.path.exists(index_path):
        return jsonify({'error': 'Index not found'}), 404
    
    try:
        # Create a new conversation if none provided
        if not conversation_id:
            conversation_id = create_conversation(index_dir, config.CONVERSATIONS_DIR)
        else:
            # Validate that the conversation exists
            if not get_conversation(conversation_id, index_dir, config.CONVERSATIONS_DIR):
                conversation_id = create_conversation(index_dir, config.CONVERSATIONS_DIR)
        
        # Add user message to the conversation
        add_message(conversation_id, index_dir, config.CONVERSATIONS_DIR, "user", query_text)
        
        # Get previous conversation for context if available
        conversation = get_conversation(conversation_id, index_dir, config.CONVERSATIONS_DIR)
        conversation_context = ""
        
        if conversation and len(conversation.get("messages", [])) > 0:
            # Format previous messages as context (limit to last 5 for brevity)
            prev_messages = conversation.get("messages", [])[-5:-1] if len(conversation.get("messages", [])) > 1 else []
            if prev_messages:
                conversation_context = "Previous conversation:\n"
                for msg in prev_messages:
                    role = "User" if msg.get("role") == "user" else "Assistant"
                    conversation_context += f"{role}: {msg.get('content')}\n\n"
        
        # Create job parameters
        job_params = {
            'index_dir': index_dir,
            'query': query_text,
            'conversation_id': conversation_id,
            'conversation_context': conversation_context
        }
        
        # Create background job
        job_id = create_job('explanation', job_params)
        
        return jsonify({
            'job_id': job_id,
            'status': JobStatus.QUEUED,
            'conversation_id': conversation_id,
            'queue_position': get_queue_position(job_id)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/compare-async', methods=['POST'])
def compare_async():
    """API endpoint for queuing an asynchronous comparison request"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Get comparison parameters
    data = request.json
    index1_dir = data.get('index1_dir')
    index2_dir = data.get('index2_dir')
    variable1 = data.get('variable1')
    variable2 = data.get('variable2')
    
    if not all([index1_dir, index2_dir, variable1, variable2]):
        return jsonify({'error': 'Missing required parameters'}), 400
    
    try:
        # Verify indexes exist
        index1_path = os.path.join(config.INDEXES_DIR, index1_dir)
        index2_path = os.path.join(config.INDEXES_DIR, index2_dir)
        
        if not (os.path.exists(index1_path) and os.path.exists(index2_path)):
            return jsonify({'error': 'One or both indexes not found'}), 404
        
        # Create job parameters
        job_params = {
            'index1_dir': index1_dir,
            'index2_dir': index2_dir,
            'variable1': variable1,
            'variable2': variable2
        }
        
        # Create background job
        job_id = create_job('comparison', job_params)
        
        return jsonify({
            'job_id': job_id,
            'status': JobStatus.QUEUED,
            'queue_position': get_queue_position(job_id)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/job-status/<job_id>', methods=['GET'])
def job_status(job_id):
    """API endpoint to check the status of a job"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    job = get_job(job_id)
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    response = {
        'job_id': job_id,
        'status': job['status'],
        'type': job['type'],
        'created_at': job['created_at'],
        'updated_at': job['updated_at']
    }
    
    # Add queue position if job is queued
    if job['status'] == JobStatus.QUEUED:
        response['queue_position'] = get_queue_position(job_id)
    
    # Add result if job is completed
    if job['status'] == JobStatus.COMPLETED:
        response['result'] = job['result']
    
    # Add error if job failed
    if job['status'] == JobStatus.FAILED:
        response['error'] = job['error']
    
    return jsonify(response)

# For explanation jobs, add a helper to update conversation after completion
@app.route('/api/save-explanation-result/<job_id>/<conversation_id>/<index_dir>', methods=['POST'])
def save_explanation_result(job_id, conversation_id, index_dir):
    """Save completed explanation job result to conversation history"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    job = get_job(job_id)
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    if job['status'] != JobStatus.COMPLETED:
        return jsonify({'error': 'Job not completed'}), 400
    
    if job['type'] != 'explanation':
        return jsonify({'error': 'Not an explanation job'}), 400
    
    try:
        # Get the result
        result = job['result']
        
        # Add assistant response to the conversation
        add_message(
            conversation_id, 
            index_dir, 
            config.CONVERSATIONS_DIR, 
            "assistant", 
            result["explanation"],
            result["sources"]
        )
        
        # Prune old conversations if needed
        prune_old_conversations(index_dir, config.CONVERSATIONS_DIR, config.MAX_CONVERSATIONS)
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500









<!-- Add to chat.html in the scripts section -->

<script>
    // Add this to your existing script in chat.html
    
    // Variables to track polling
    let currentJobId = null;
    let pollingInterval = null;
    
    // Handle query submission with background processing
    queryForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const query = queryInput.value.trim();
        if (!query) return;
        
        // Show loading state
        loadingElement.classList.remove('d-none');
        queryButton.disabled = true;
        queryButton.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Processing...';
        
        // Add user message to the UI immediately
        addMessageToUI('user', query);
        
        try {
            // Call the API to create an async job
            const response = await fetch(`/api/query-async/${indexDir}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    query: query,
                    conversation_id: currentConversationId
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            
            const data = await response.json();
            
            // Update conversation ID if this is a new conversation
            if (!currentConversationId) {
                currentConversationId = data.conversation_id;
                // Update URL without reloading the page
                window.history.pushState({}, '', `/chat/${indexDir}/${currentConversationId}`);
                
                // Refresh conversation list
                loadConversations();
            }
            
            // Update UI to show job is processing
            addProcessingMessage(data.job_id, data.queue_position);
            
            // Start polling for job status
            startJobPolling(data.job_id);
            
            // Clear input
            queryInput.value = '';
            
        } catch (error) {
            console.error('Error submitting query:', error);
            // Add error message to UI
            addMessageToUI('assistant', `Error: ${error.message}`);
            
            // Reset loading state
            loadingElement.classList.add('d-none');
            queryButton.disabled = false;
            queryButton.innerHTML = '<i class="fas fa-paper-plane me-1"></i> Send';
        }
    });
    
    // Function to add a processing message to the UI
    function addProcessingMessage(jobId, queuePosition) {
        // Create a placeholder for the assistant message
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message message-assistant fade-in';
        messageDiv.id = `job-${jobId}`;
        
        // Create message content
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        // Show initial status with queue position
        if (queuePosition > 1) {
            contentDiv.innerHTML = `
                <div class="d-flex align-items-center">
                    <div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>
                    <div>Your request is in queue (position ${queuePosition})...</div>
                </div>
            `;
        } else {
            contentDiv.innerHTML = `
                <div class="d-flex align-items-center">
                    <div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>
                    <div>Processing your request...</div>
                </div>
            `;
        }
        
        // Create timestamp
        const timestampDiv = document.createElement('div');
        timestampDiv.className = 'message-timestamp';
        timestampDiv.textContent = new Date().toLocaleTimeString();
        
        // Assemble message
        messageDiv.appendChild(contentDiv);
        messageDiv.appendChild(timestampDiv);
        
        // Add to conversation container
        conversationContainer.appendChild(messageDiv);
        
        // Scroll to bottom
        conversationContainer.scrollTop = conversationContainer.scrollHeight;
    }
    
    // Function to update processing message
    function updateProcessingMessage(jobId, status, queuePosition = null) {
        const messageDiv = document.getElementById(`job-${jobId}`);
        if (!messageDiv) return;
        
        const contentDiv = messageDiv.querySelector('.message-content');
        
        if (status === 'queued' && queuePosition) {
            contentDiv.innerHTML = `
                <div class="d-flex align-items-center">
                    <div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>
                    <div>Your request is in queue (position ${queuePosition})...</div>
                </div>
            `;
        } else if (status === 'processing') {
            contentDiv.innerHTML = `
                <div class="d-flex align-items-center">
                    <div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>
                    <div>Processing your request...</div>
                </div>
            `;
        }
    }
    
    // Function to start polling for job status
    function startJobPolling(jobId) {
        // Store current job ID
        currentJobId = jobId;
        
        // Clear any existing polling
        if (pollingInterval) {
            clearInterval(pollingInterval);
        }
        
        // Define polling function
        const pollJobStatus = async () => {
            try {
                const response = await fetch(`/api/job-status/${jobId}`);
                
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                
                const data = await response.json();
                
                // Update UI based on job status
                if (data.status === 'queued') {
                    updateProcessingMessage(jobId, 'queued', data.queue_position);
                } else if (data.status === 'processing') {
                    updateProcessingMessage(jobId, 'processing');
                } else if (data.status === 'completed') {
                    // Clear polling
                    clearInterval(pollingInterval);
                    pollingInterval = null;
                    currentJobId = null;
                    
                    // Replace processing message with result
                    replaceWithResult(jobId, data.result);
                    
                    // Save to conversation history
                    saveExplanationResult(jobId);
                    
                    // Reset loading state
                    loadingElement.classList.add('d-none');
                    queryButton.disabled = false;
                    queryButton.innerHTML = '<i class="fas fa-paper-plane me-1"></i> Send';
                    
                    // Focus input for next message
                    queryInput.focus();
                } else if (data.status === 'failed') {
                    // Clear polling
                    clearInterval(pollingInterval);
                    pollingInterval = null;
                    currentJobId = null;
                    
                    // Replace with error message
                    const messageDiv = document.getElementById(`job-${jobId}`);
                    if (messageDiv) {
                        const contentDiv = messageDiv.querySelector('.message-content');
                        contentDiv.innerHTML = `<div class="alert alert-danger">Error: ${data.error || 'Job processing failed'}</div>`;
                    }
                    
                    // Reset loading state
                    loadingElement.classList.add('d-none');
                    queryButton.disabled = false;
                    queryButton.innerHTML = '<i class="fas fa-paper-plane me-1"></i> Send';
                }
            } catch (error) {
                console.error('Error polling job status:', error);
            }
        };
        
        // Start polling
        pollingInterval = setInterval(pollJobStatus, 2000);
        
        // Poll immediately
        pollJobStatus();
    }
    
    // Function to replace processing message with result
    function replaceWithResult(jobId, result) {
        const messageDiv = document.getElementById(`job-${jobId}`);
        if (!messageDiv) return;
        
        // Remove the message div and add a new message with the result
        messageDiv.remove();
        
        // Add assistant message with the result
        addMessageToUI('assistant', result.explanation, result.sources);
    }
    
    // Function to save explanation result to conversation history
    async function saveExplanationResult(jobId) {
        try {
            const response = await fetch(`/api/save-explanation-result/${jobId}/${currentConversationId}/${indexDir}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) {
                console.error('Error saving explanation result');
            }
        } catch (error) {
            console.error('Error saving explanation result:', error);
        }
    }
    
    // Add event listener to handle page exit while a job is running
    window.addEventListener('beforeunload', function(e) {
        if (currentJobId) {
            // Show a confirmation dialog
            const confirmationMessage = 'You have a query processing. Are you sure you want to leave?';
            e.returnValue = confirmationMessage;
            return confirmationMessage;
        }
    });
</script>








<!-- Update compare.html script section -->

<script>
    document.addEventListener('DOMContentLoaded', function() {
        const comparisonForm = document.getElementById('comparison-form');
        const compareBtn = document.getElementById('compare-btn');
        const resultsContainer = document.getElementById('results-container');
        const loadingElement = document.getElementById('loading');
        const index1Select = document.getElementById('index1');
        const index2Select = document.getElementById('index2');
        const variable1Input = document.getElementById('variable1');
        const variable2Input = document.getElementById('variable2');
        const lang1Badge = document.getElementById('lang1-badge');
        const lang2Badge = document.getElementById('lang2-badge');
        
        // Variables to track polling
        let currentJobId = null;
        let pollingInterval = null;
        
        // Update language badges when indexes are selected
        index1Select.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            const language = selectedOption.getAttribute('data-language');
            lang1Badge.innerHTML = `<span class="badge bg-primary">${language}</span>`;
        });
        
        index2Select.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            const language = selectedOption.getAttribute('data-language');
            lang2Badge.innerHTML = `<span class="badge bg-primary">${language}</span>`;
        });
        
        // Handle comparison form submission
        comparisonForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const index1Dir = index1Select.value;
            const index2Dir = index2Select.value;
            const variable1 = variable1Input.value.trim();
            const variable2 = variable2Input.value.trim();
            
            if (!index1Dir || !index2Dir || !variable1 || !variable2) {
                alert('Please fill in all required fields');
                return;
            }
            
            // Show loading state
            loadingElement.classList.remove('d-none');
            compareBtn.disabled = true;
            compareBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Submitting...';
            
            try {
                // Call the API to create a background job
                const response = await fetch('/api/compare-async', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        index1_dir: index1Dir,
                        index2_dir: index2Dir,
                        variable1: variable1,
                        variable2: variable2
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                
                const data = await response.json();
                
                // Update UI to show job status
                showJobStatus(data.job_id, data.queue_position);
                
                // Start polling for job status
                startJobPolling(data.job_id);
                
            } catch (error) {
                console.error('Error submitting comparison:', error);
                alert(`Error: ${error.message}`);
                
                // Reset loading state
                loadingElement.classList.add('d-none');
                compareBtn.disabled = false;
                compareBtn.innerHTML = '<i class="fas fa-code-compare me-2"></i>Compare Implementations';
            }
        });
        
        // Function to show job status
        function showJobStatus(jobId, queuePosition) {
            // Show results container with status
            resultsContainer.classList.remove('d-none');
            
            // Update comparison title to show status
            const statusTitle = document.getElementById('comparison-title');
            
            if (queuePosition > 1) {
                statusTitle.innerHTML = `
                    <i class="fas fa-spinner fa-spin me-2 text-primary"></i>
                    Job queued (position ${queuePosition}) - Please wait...
                `;
            } else {
                statusTitle.innerHTML = `
                    <i class="fas fa-spinner fa-spin me-2 text-primary"></i>
                    Processing comparison - Please wait...
                `;
            }
            
            // Clear previous content
            document.getElementById('comparison-content').innerHTML = `
                <div class="text-center py-4">
                    <div class="spinner-border text-primary mb-3" role="status" style="width: 3rem; height: 3rem;">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <p class="mb-0">Analyzing code and generating comparison...</p>
                    <p class="text-muted small">This may take a minute or two.</p>
                </div>
            `;
            
            // Clear sources
            document.getElementById('sources1-accordion').innerHTML = '';
            document.getElementById('sources2-accordion').innerHTML = '';
            
            // Update source titles
            document.getElementById('sources1-title').innerHTML = `
                <i class="fas fa-spinner fa-spin me-2 text-primary"></i>
                Loading first variable sources...
            `;
            
            document.getElementById('sources2-title').innerHTML = `
                <i class="fas fa-spinner fa-spin me-2 text-primary"></i>
                Loading second variable sources...
            `;
            
            // Store the job ID
            currentJobId = jobId;
        }
        
        // Function to update job status
        function updateJobStatus(status, queuePosition = null) {
            const statusTitle = document.getElementById('comparison-title');
            
            if (status === 'queued' && queuePosition) {
                statusTitle.innerHTML = `
                    <i class="fas fa-spinner fa-spin me-2 text-primary"></i>
                    Job queued (position ${queuePosition}) - Please wait...
                `;
            } else if (status === 'processing') {
                statusTitle.innerHTML = `
                    <i class="fas fa-spinner fa-spin me-2 text-primary"></i>
                    Processing comparison - Please wait...
                `;
            }
        }
        
        // Function to start polling for job status
        function startJobPolling(jobId) {
            // Clear any existing polling
            if (pollingInterval) {
                clearInterval(pollingInterval);
            }
            
            // Define polling function
            const pollJobStatus = async () => {
                try {
                    const response = await fetch(`/api/job-status/${jobId}`);
                    
                    if (!response.ok) {
                        throw new Error(`HTTP error! Status: ${response.status}`);
                    }
                    
                    const data = await response.json();
                    
                    // Update UI based on job status
                    if (data.status === 'queued') {
                        updateJobStatus('queued', data.queue_position);
                    } else if (data.status === 'processing') {
                        updateJobStatus('processing');
                    } else if (data.status === 'completed') {
                        // Clear polling
                        clearInterval(pollingInterval);
                        pollingInterval = null;
                        currentJobId = null;
                        
                        // Display results
                        displayResults(data.result);
                        
                        // Reset loading state
                        loadingElement.classList.add('d-none');
                        compareBtn.disabled = false;
                        compareBtn.innerHTML = '<i class="fas fa-code-compare me-2"></i>Compare Implementations';
                        
                        // Scroll to results
                        resultsContainer.scrollIntoView({ behavior: 'smooth' });
                    } else if (data.status === 'failed') {
                        // Clear polling
                        clearInterval(pollingInterval);
                        pollingInterval = null;
                        currentJobId = null;
                        
                        // Show error
                        document.getElementById('comparison-title').innerHTML = `
                            <i class="fas fa-exclamation-triangle me-2 text-danger"></i>
                            Error Processing Comparison
                        `;
                        
                        document.getElementById('comparison-content').innerHTML = `
                            <div class="alert alert-danger">
                                <strong>Error:</strong> ${data.error || 'An unknown error occurred during comparison.'}
                            </div>
                            <p>Please try again or try with different variables.</p>
                        `;
                        
                        // Reset loading state
                        loadingElement.classList.add('d-none');
                        compareBtn.disabled = false;
                        compareBtn.innerHTML = '<i class="fas fa-code-compare me-2"></i>Compare Implementations';
                    }
                } catch (error) {
                    console.error('Error polling job status:', error);
                }
            };
            
            // Start polling
            pollingInterval = setInterval(pollJobStatus, 2000);
            
            // Poll immediately
            pollJobStatus();
        }
        
        // Function to display comparison results
        function displayResults(data) {
            // Update comparison titles
            document.getElementById('comparison-title').innerHTML = 
                `<i class="fas fa-lightbulb me-2 text-primary"></i>Comparison Analysis: ${data.variable1} vs ${data.variable2}`;
            
            document.getElementById('sources1-title').innerHTML = 
                `<i class="fas fa-code me-2 text-primary"></i>${data.variable1} in ${data.repo1} (${data.language1})`;
            
            document.getElementById('sources2-title').innerHTML = 
                `<i class="fas fa-code me-2 text-primary"></i>${data.variable2} in ${data.repo2} (${data.language2})`;
            
            // Display comparison text
            const comparisonContent = document.getElementById('comparison-content');
            comparisonContent.innerHTML = formatExplanation(data.comparison);
            
            // Display sources for first variable
            const sources1Accordion = document.getElementById('sources1-accordion');
            sources1Accordion.innerHTML = '';
            
            data.sources1.forEach((source, index) => {
                const accordionItem = createSourceAccordionItem(
                    source, 
                    index, 
                    'sources1', 
                    data.language1.toLowerCase()
                );
                sources1Accordion.appendChild(accordionItem);
            });
            
            // Display sources for second variable
            const sources2Accordion = document.getElementById('sources2-accordion');
            sources2Accordion.innerHTML = '';
            
            data.sources2.forEach((source, index) => {
                const accordionItem = createSourceAccordionItem(
                    source, 
                    index, 
                    'sources2', 
                    data.language2.toLowerCase()
                );
                sources2Accordion.appendChild(accordionItem);
            });
            
            // Initialize syntax highlighting
            document.querySelectorAll('pre code').forEach((block) => {
                hljs.highlightElement(block);
            });
        }
        
        // Function to create source accordion item
        function createSourceAccordionItem(source, index, prefix, language) {
            const accordionItem = document.createElement('div');
            accordionItem.className = 'accordion-item';
            
            const header = document.createElement('h2');
            header.className = 'accordion-header';
            
            const button = document.createElement('button');
            button.className = 'accordion-button collapsed';
            button.type = 'button';
            button.setAttribute('data-bs-toggle', 'collapse');
            button.setAttribute('data-bs-target', `#${prefix}-source-${index}`);
            button.innerHTML = `
                <div class="d-flex w-100 justify-content-between align-items-center">
                    <div>
                        <i class="fas fa-file-code me-2 text-primary"></i>
                        <strong>${source.path}</strong>
                    </div>
                </div>
            `;
            
            const collapseDiv = document.createElement('div');
            collapseDiv.id = `${prefix}-source-${index}`;
            collapseDiv.className = 'accordion-collapse collapse';
            
            const accordionBody = document.createElement('div');
            accordionBody.className = 'accordion-body p-0';
            
            const pre = document.createElement('pre');
            pre.className = 'm-0';
            
            const code = document.createElement('code');
            code.className = `language-${getLanguageFromPath(source.path, language)}`;
            code.textContent = source.content;
            
            pre.appendChild(code);
            accordionBody.appendChild(pre);
            collapseDiv.appendChild(accordionBody);
            header.appendChild(button);
            accordionItem.appendChild(header);
            accordionItem.appendChild(collapseDiv);
            
            return accordionItem;
        }
        
        // Function to format explanation text with markdown-like formatting
        function formatExplanation(text) {
            // Simple markdown-like formatting
            let formatted = text
                // Code blocks
                .replace(/```([a-z]*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
                // Inline code
                .replace(/`([^`]+)`/g, '<code>$1</code>')
                // Bold
                .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                // Italic
                .replace(/\*([^*]+)\*/g, '<em>$1</em>')
                // Headers
                .replace(/^### (.*$)/gm, '<h5>$1</h5>')
                .replace(/^## (.*$)/gm, '<h4>$1</h4>')
                .replace(/^# (.*$)/gm, '<h3>$1</h3>')
                // Lists
                .replace(/^\s*- (.*$)/gm, '<li>$1</li>')
                .replace(/^\s*\d+\. (.*$)/gm, '<li>$1</li>')
                // Wrap lists
                .replace(/<li>(.*)<\/li>\n<li>/g, '<li>$1</li>\n<li>')
                .replace(/(<li>.*<\/li>\n)+/g, '<ul>$&</ul>')
                // Paragraphs
                .replace(/\n\n/g, '</p><p>');
            
            // Wrap in paragraph tags if not already
            if (!formatted.startsWith('<')) {
                formatted = '<p>' + formatted + '</p>';
            }
            
            return formatted;
        }
        
        // Function to determine language from file path
        function getLanguageFromPath(path, defaultLanguage) {
            const extension = path.split('.').pop().toLowerCase();
            
            const extensionToLanguage = {
                'py': 'python',
                'js': 'javascript',
                'jsx': 'javascript',
                'ts': 'typescript',
                'tsx': 'typescript',
                'java': 'java',
                'c': 'c',
                'cpp': 'cpp',
                'h': 'cpp',
                'hpp': 'cpp',
                'cc': 'cpp',
                'cs': 'csharp',
                'go': 'go',
                'rb': 'ruby',
                'php': 'php',
                'rs': 'rust',
                'swift': 'swift',
                'kt': 'kotlin',
                'kts': 'kotlin',
                'scala': 'scala'
            };
            
            return extensionToLanguage[extension] || defaultLanguage || 'plaintext';
        }
        
        // Add event listener to handle page exit while a job is running
        window.addEventListener('beforeunload', function(e) {
            if (currentJobId) {
                // Show a confirmation dialog
                const confirmationMessage = 'You have a comparison job processing. Are you sure you want to leave?';
                e.returnValue = confirmationMessage;
                return confirmationMessage;
            }
        });
    });
</script>








<!-- Add a job status widget to dashboard.html before the repository list -->

<div class="row mb-4">
    <div class="col-12">
        <div class="card shadow">
            <div class="card-header">
                <h5 class="mb-0">
                    <i class="fas fa-tasks me-2 text-primary"></i>Background Jobs
                </h5>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-8">
                        <div id="job-status-counts" class="d-flex">
                            <div class="me-4">
                                <span class="d-block fw-bold fs-3" id="queued-count">-</span>
                                <span class="text-muted">Queued</span>
                            </div>
                            <div class="me-4">
                                <span class="d-block fw-bold fs-3" id="processing-count">-</span>
                                <span class="text-muted">Processing</span>
                            </div>
                            <div class="me-4">
                                <span class="d-block fw-bold fs-3" id="completed-count">-</span>
                                <span class="text-muted">Completed</span>
                            </div>
                            <div>
                                <span class="d-block fw-bold fs-3" id="failed-count">-</span>
                                <span class="text-muted">Failed</span>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-4 text-md-end mt-3 mt-md-0">
                        <button id="refresh-job-status" class="btn btn-outline-primary">
                            <i class="fas fa-sync-alt me-2"></i>Refresh Status
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Add a new API endpoint to app.py -->
<!-- @app.route('/api/job-counts', methods=['GET'])
def job_counts():
    """API endpoint to get job counts by status"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    from utils.background import get_job_count
    
    queued, processing, completed, failed = get_job_count()
    
    return jsonify({
        'queued': queued,
        'processing': processing,
        'completed': completed,
        'failed': failed
    })
-->

<!-- Add this script to the scripts block in dashboard.html -->
<script>
    document.addEventListener('DOMContentLoaded', function() {
        const refreshJobStatusBtn = document.getElementById('refresh-job-status');
        
        // Load job status on page load
        loadJobStatus();
        
        // Set up refresh button
        refreshJobStatusBtn.addEventListener('click', function() {
            this.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Refreshing...';
            this.disabled = true;
            
            loadJobStatus().finally(() => {
                this.innerHTML = '<i class="fas fa-sync-alt me-2"></i>Refresh Status';
                this.disabled = false;
            });
        });
        
        // Function to load job status
        async function loadJobStatus() {
            try {
                const response = await fetch('/api/job-counts');
                
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                
                const data = await response.json();
                
                // Update the UI
                document.getElementById('queued-count').textContent = data.queued;
                document.getElementById('processing-count').textContent = data.processing;
                document.getElementById('completed-count').textContent = data.completed;
                document.getElementById('failed-count').textContent = data.failed;
                
            } catch (error) {
                console.error('Error loading job status:', error);
                
                // Show error in the UI
                document.getElementById('queued-count').textContent = '-';
                document.getElementById('processing-count').textContent = '-';
                document.getElementById('completed-count').textContent = '-';
                document.getElementById('failed-count').textContent = '-';
            }
        }
    });
</script>








#app.py route

@app.route('/api/job-counts', methods=['GET'])
def job_counts():
    """API endpoint to get job counts by status"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    from utils.background import get_job_count
    
    queued, processing, completed, failed = get_job_count()
    
    return jsonify({
        'queued': queued,
        'processing': processing,
        'completed': completed,
        'failed': failed
    })
