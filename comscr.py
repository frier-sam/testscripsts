<!-- Find the Repository Info section in chat.html and update it -->
<!-- Around line 80-95 in the original file -->
<!-- Repository Info -->
<div class="card mb-3">
    <div class="card-body py-2">
        <div class="d-flex justify-content-between align-items-center">
            <div>
                <h5 class="mb-0">{{ metadata.name }}</h5>
                <div class="text-muted small">
                    <span class="badge bg-primary">{{ metadata.language }}</span>
                    <span class="badge bg-secondary">{{ metadata.num_documents }} files</span>
                </div>
            </div>
            <div class="d-flex">
                {% if conversation %}
                <a href="{{ url_for('compare', index_dir=index_dir, conversation_id=conversation.id) }}" class="btn btn-outline-primary me-2">
                    <i class="fas fa-exchange-alt me-1"></i>Compare
                </a>
                {% endif %}
                <div id="conversation-title" class="text-end">
                    {% if conversation %}
                        <span class="text-primary fw-bold">{{ conversation.title }}</span>
                        <div class="text-muted small">Started: {{ conversation.created_at }}</div>
                    {% else %}
                        <span class="text-primary fw-bold">New Conversation</span>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>
</div>




<!-- templates/comparison.html -->
{% extends "layout.html" %}

{% block title %}Compare Conversations - Zenassist{% endblock %}

{% block content %}
<div class="row align-items-center mb-4">
    <div class="col">
        <h1 class="display-5">
            <i class="fas fa-exchange-alt me-2 text-primary"></i>Compare Conversations
        </h1>
        <p class="lead">Compare different code repositories to understand differences and similarities</p>
    </div>
    <div class="col-auto">
        <a href="{{ url_for('chat', index_dir=index_dir, conversation_id=conversation_id) }}" class="btn btn-outline-primary">
            <i class="fas fa-arrow-left me-2"></i>Back to Chat
        </a>
    </div>
</div>

<div class="row">
    <div class="col-md-6 mb-4">
        <div class="card shadow h-100">
            <div class="card-header">
                <h5 class="card-title mb-0">
                    <i class="fas fa-code me-2 text-primary"></i>First Repository
                </h5>
            </div>
            <div class="card-body">
                <!-- First conversation selector -->
                <div class="mb-4">
                    <label class="form-label">Repository</label>
                    <select class="form-select" id="first-index" disabled>
                        {% for index in indexes %}
                            <option value="{{ index.directory }}" {% if index.directory == index_dir %}selected{% endif %}>
                                {{ index.name }}
                            </option>
                        {% endfor %}
                    </select>
                    <div class="form-text">Current repository is pre-selected</div>
                </div>
                
                <div class="mb-4">
                    <label class="form-label">Conversation</label>
                    <select class="form-select" id="first-conversation" disabled>
                        {% for conv in conversations %}
                            <option value="{{ conv.id }}" {% if conv.id == conversation_id %}selected{% endif %}>
                                {{ conv.title }}
                            </option>
                        {% endfor %}
                    </select>
                    <div class="form-text">Current conversation is pre-selected</div>
                </div>
                
                <div class="border-top pt-3 mt-3">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h6 class="mb-0">Conversation Preview</h6>
                    </div>
                    
                    <div class="conversation-preview">
                        {% if conv_preview1 %}
                            {% for message in conv_preview1 %}
                            <div class="preview-message mb-2">
                                <div class="preview-badge {% if message.role == 'user' %}bg-primary{% else %}bg-secondary{% endif %}">
                                    {{ message.role|capitalize }}
                                </div>
                                <div class="preview-content">
                                    {{ message.content|truncate(100) }}
                                </div>
                            </div>
                            {% endfor %}
                        {% else %}
                            <div class="text-center text-muted py-3">
                                <i class="fas fa-comment-slash fa-2x mb-2"></i>
                                <p>No messages to preview</p>
                            </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="col-md-6 mb-4">
        <div class="card shadow h-100">
            <div class="card-header">
                <h5 class="card-title mb-0">
                    <i class="fas fa-code me-2 text-primary"></i>Second Repository
                </h5>
            </div>
            <div class="card-body">
                <!-- Second conversation selector -->
                <div class="mb-4">
                    <label class="form-label">Repository</label>
                    <select class="form-select" id="second-index">
                        <option value="" selected disabled>Select a repository...</option>
                        {% for index in indexes %}
                            <option value="{{ index.directory }}">
                                {{ index.name }}
                            </option>
                        {% endfor %}
                    </select>
                </div>
                
                <div class="mb-4">
                    <label class="form-label">Conversation</label>
                    <select class="form-select" id="second-conversation" disabled>
                        <option value="" selected disabled>Select a repository first</option>
                    </select>
                </div>
                
                <div class="border-top pt-3 mt-3">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h6 class="mb-0">Conversation Preview</h6>
                    </div>
                    
                    <div class="conversation-preview" id="second-conversation-preview">
                        <div class="text-center text-muted py-3">
                            <i class="fas fa-comment-slash fa-2x mb-2"></i>
                            <p>Select a conversation to preview</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<div class="row">
    <div class="col-12">
        <div class="card shadow">
            <div class="card-header">
                <h5 class="card-title mb-0">
                    <i class="fas fa-search-plus me-2 text-primary"></i>Comparison Results
                </h5>
            </div>
            <div class="card-body" id="comparison-results">
                <div class="text-center py-5">
                    <i class="fas fa-exchange-alt fa-3x mb-3 text-muted"></i>
                    <h4 class="text-muted">Select repositories and conversations to compare</h4>
                    <p class="text-muted mb-4">The AI will analyze both conversations and provide insights on similarities and differences.</p>
                    <button id="compare-btn" class="btn btn-primary btn-lg" disabled>
                        <i class="fas fa-exchange-alt me-2"></i>Compare Conversations
                    </button>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Loading Indicator -->
<div id="loading" class="position-fixed top-50 start-50 translate-middle d-none" style="z-index: 1050;">
    <div class="bg-white p-4 rounded shadow-lg text-center">
        <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;">
            <span class="visually-hidden">Loading...</span>
        </div>
        <p class="mt-3 mb-0">Comparing conversations...</p>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
    document.addEventListener('DOMContentLoaded', function() {
        const secondIndexSelect = document.getElementById('second-index');
        const secondConversationSelect = document.getElementById('second-conversation');
        const secondConversationPreview = document.getElementById('second-conversation-preview');
        const compareBtn = document.getElementById('compare-btn');
        const loadingElement = document.getElementById('loading');
        const comparisonResults = document.getElementById('comparison-results');
        
        // When user selects a repository, load conversations
        secondIndexSelect.addEventListener('change', async function() {
            const indexDir = this.value;
            if (!indexDir) return;
            
            secondConversationSelect.innerHTML = '<option value="" selected disabled>Loading conversations...</option>';
            secondConversationSelect.disabled = true;
            
            try {
                const response = await fetch(`/api/conversations/${indexDir}`);
                if (!response.ok) {
                    throw new Error('Failed to load conversations');
                }
                
                const conversations = await response.json();
                
                secondConversationSelect.innerHTML = '<option value="" selected disabled>Select a conversation...</option>';
                
                if (conversations.length === 0) {
                    secondConversationSelect.innerHTML = '<option value="" disabled>No conversations available</option>';
                } else {
                    conversations.forEach(conv => {
                        const option = document.createElement('option');
                        option.value = conv.id;
                        option.textContent = conv.title;
                        secondConversationSelect.appendChild(option);
                    });
                    secondConversationSelect.disabled = false;
                }
            } catch (error) {
                console.error('Error loading conversations:', error);
                secondConversationSelect.innerHTML = '<option value="" disabled>Error loading conversations</option>';
            }
        });
        
        // When user selects a conversation, load preview and enable compare button
        secondConversationSelect.addEventListener('change', async function() {
            const conversationId = this.value;
            const indexDir = secondIndexSelect.value;
            
            if (!conversationId || !indexDir) return;
            
            try {
                const response = await fetch(`/api/conversations/${indexDir}/${conversationId}`);
                if (!response.ok) {
                    throw new Error('Failed to load conversation preview');
                }
                
                const conversation = await response.json();
                
                // Display preview
                secondConversationPreview.innerHTML = '';
                
                if (!conversation.messages || conversation.messages.length === 0) {
                    secondConversationPreview.innerHTML = `
                        <div class="text-center text-muted py-3">
                            <i class="fas fa-comment-slash fa-2x mb-2"></i>
                            <p>No messages in this conversation</p>
                        </div>
                    `;
                } else {
                    // Show up to 5 messages
                    const previewMessages = conversation.messages.slice(0, 5);
                    
                    previewMessages.forEach(message => {
                        const messageDiv = document.createElement('div');
                        messageDiv.className = 'preview-message mb-2';
                        
                        const badgeClass = message.role === 'user' ? 'bg-primary' : 'bg-secondary';
                        
                        messageDiv.innerHTML = `
                            <div class="preview-badge ${badgeClass}">
                                ${message.role.charAt(0).toUpperCase() + message.role.slice(1)}
                            </div>
                            <div class="preview-content">
                                ${truncateText(message.content, 100)}
                            </div>
                        `;
                        
                        secondConversationPreview.appendChild(messageDiv);
                    });
                    
                    // Enable compare button
                    compareBtn.disabled = false;
                }
            } catch (error) {
                console.error('Error loading conversation preview:', error);
                secondConversationPreview.innerHTML = `
                    <div class="text-center text-danger py-3">
                        <i class="fas fa-exclamation-circle fa-2x mb-2"></i>
                        <p>Error loading conversation preview</p>
                    </div>
                `;
            }
        });
        
        // Handle compare button click
        compareBtn.addEventListener('click', async function() {
            const firstIndexDir = document.getElementById('first-index').value;
            const firstConversationId = document.getElementById('first-conversation').value;
            const secondIndexDir = secondIndexSelect.value;
            const secondConversationId = secondConversationSelect.value;
            
            if (!firstIndexDir || !firstConversationId || !secondIndexDir || !secondConversationId) {
                alert('Please select both conversations to compare');
                return;
            }
            
            // Show loading
            loadingElement.classList.remove('d-none');
            compareBtn.disabled = true;
            
            try {
                const response = await fetch('/api/compare', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        first_index: firstIndexDir,
                        first_conversation: firstConversationId,
                        second_index: secondIndexDir,
                        second_conversation: secondConversationId
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                
                const data = await response.json();
                
                // Display comparison results
                comparisonResults.innerHTML = `
                    <div class="comparison-result">
                        <h4 class="mb-3">Comparison Analysis</h4>
                        <div class="mb-4">
                            ${formatComparisonText(data.comparison)}
                        </div>
                    </div>
                `;
            } catch (error) {
                console.error('Error comparing conversations:', error);
                comparisonResults.innerHTML = `
                    <div class="text-center text-danger py-3">
                        <i class="fas fa-exclamation-circle fa-3x mb-3"></i>
                        <h4>Error Comparing Conversations</h4>
                        <p>${error.message}</p>
                        <button class="btn btn-primary mt-3" onclick="location.reload()">
                            <i class="fas fa-redo me-2"></i>Try Again
                        </button>
                    </div>
                `;
            } finally {
                // Hide loading
                loadingElement.classList.add('d-none');
                compareBtn.disabled = false;
            }
        });
        
        // Helper function to truncate text
        function truncateText(text, maxLength = 100) {
            if (text.length <= maxLength) return text;
            return text.substring(0, maxLength) + '...';
        }
        
        // Helper function to format comparison text
        function formatComparisonText(text) {
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
    });
</script>

<style>
    .conversation-preview {
        max-height: 300px;
        overflow-y: auto;
        background-color: var(--gray-50);
        border-radius: var(--border-radius);
        padding: 1rem;
    }
    
    .preview-message {
        display: flex;
        align-items: flex-start;
        gap: 0.5rem;
    }
    
    .preview-badge {
        flex-shrink: 0;
        font-size: 0.75rem;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        color: white;
    }
    
    .preview-content {
        background-color: white;
        padding: 0.5rem 0.75rem;
        border-radius: 0.5rem;
        flex-grow: 1;
        font-size: 0.9rem;
    }
    
    .comparison-result p {
        margin-bottom: 1rem;
    }
    
    .comparison-result h3, .comparison-result h4, .comparison-result h5 {
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
    }
    
    .comparison-result code {
        background-color: var(--gray-100);
        padding: 0.2rem 0.4rem;
        border-radius: 0.25rem;
        font-family: 'JetBrains Mono', 'Fira Code', 'Roboto Mono', 'Courier New', monospace;
        font-size: 0.9rem;
        color: var(--primary-dark);
    }
    
    .comparison-result pre {
        background-color: var(--gray-900);
        color: white;
        padding: 1rem;
        border-radius: var(--border-radius);
        overflow-x: auto;
        margin: 1rem 0;
    }
</style>
{% endblock %}








# Add these imports at the top of app.py if not already present
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import json

# Add these route handlers to app.py

@app.route('/compare/<index_dir>/<conversation_id>')
def compare(index_dir, conversation_id):
    """Comparison page for analyzing two conversations"""
    if not session.get('logged_in'):
        flash('Please log in first', 'warning')
        return redirect(url_for('login'))
    
    # Load the index metadata
    index_path = os.path.join(config.INDEXES_DIR, index_dir)
    
    if not os.path.exists(index_path):
        flash('Index not found', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # Get the conversation
        conversation = get_conversation(conversation_id, index_dir, config.CONVERSATIONS_DIR)
        
        if not conversation:
            flash('Conversation not found', 'warning')
            return redirect(url_for('chat', index_dir=index_dir))
        
        # Get all available indexes
        indexes = get_all_indexes(config.INDEXES_DIR)
        
        # Get conversations for this index
        conversations = get_conversations(index_dir, config.CONVERSATIONS_DIR)
        
        # Get a preview of the first conversation (first 5 messages)
        conv_preview1 = conversation.get('messages', [])[:5]
        
        return render_template(
            'comparison.html',
            index_dir=index_dir,
            conversation_id=conversation_id,
            indexes=indexes,
            conversations=conversations,
            conv_preview1=conv_preview1
        )
    
    except Exception as e:
        flash(f'Error loading comparison: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/api/compare', methods=['POST'])
def api_compare():
    """API endpoint for comparing two conversations"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Get request data
    data = request.json
    first_index = data.get('first_index')
    first_conversation = data.get('first_conversation')
    second_index = data.get('second_index')
    second_conversation = data.get('second_conversation')
    
    if not all([first_index, first_conversation, second_index, second_conversation]):
        return jsonify({'error': 'Missing required parameters'}), 400
    
    try:
        # Get first conversation
        conv1 = get_conversation(first_conversation, first_index, config.CONVERSATIONS_DIR)
        if not conv1:
            return jsonify({'error': 'First conversation not found'}), 404
        
        # Get second conversation
        conv2 = get_conversation(second_conversation, second_index, config.CONVERSATIONS_DIR)
        if not conv2:
            return jsonify({'error': 'Second conversation not found'}), 404
        
        # Get index metadata
        with open(os.path.join(config.INDEXES_DIR, first_index, 'metadata.json'), 'r') as f:
            first_metadata = json.load(f)
        
        with open(os.path.join(config.INDEXES_DIR, second_index, 'metadata.json'), 'r') as f:
            second_metadata = json.load(f)
        
        # Extract messages without sources
        first_messages = [
            {'role': msg.get('role'), 'content': msg.get('content')} 
            for msg in conv1.get('messages', [])
        ]
        
        second_messages = [
            {'role': msg.get('role'), 'content': msg.get('content')} 
            for msg in conv2.get('messages', [])
        ]
        
        # Format conversations for the LLM
        first_convo_formatted = "\n".join([
            f"{msg['role'].capitalize()}: {msg['content']}" 
            for msg in first_messages
        ])
        
        second_convo_formatted = "\n".join([
            f"{msg['role'].capitalize()}: {msg['content']}" 
            for msg in second_messages
        ])
        
        # Create the prompt for comparison
        comparison_prompt = f"""
You are an expert code assistant called Zenassist. You are analyzing two different conversations about code repositories.

FIRST REPOSITORY: {first_metadata.get('name')} ({first_metadata.get('language')})
FIRST CONVERSATION:
{first_convo_formatted}

SECOND REPOSITORY: {second_metadata.get('name')} ({second_metadata.get('language')})
SECOND CONVERSATION:
{second_convo_formatted}

Compare these two conversations and provide an insightful analysis focusing on:
1. The main topics/questions discussed in each conversation
2. Key similarities and differences between the code repositories based on the conversations
3. Any interesting patterns or relationships between the two codebases
4. Potential insights that might be helpful when working with both repositories together

Organize your analysis in a clear, structured format with headers and sections.
"""
        
        # Query the LLM
        payload = {
            "prompt": comparison_prompt,
            "max_tokens": 1024,  # Increased token limit for detailed comparison
            "temperature": 0.3,
            "model": config.VLLM_MODEL
        }
        
        response = requests.post(config.VLLM_ENDPOINT, json=payload)
        response.raise_for_status()
        result = response.json()
        
        comparison_text = result.get("generated_text", "Unable to generate comparison")
        
        return jsonify({
            'first_repository': first_metadata.get('name'),
            'second_repository': second_metadata.get('name'),
            'comparison': comparison_text
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Add this route to get specific conversation data
@app.route('/api/conversations/<index_dir>/<conversation_id>', methods=['GET'])
def get_conversation_data(index_dir, conversation_id):
    """API endpoint to get a specific conversation"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Get the conversation
    conversation = get_conversation(conversation_id, index_dir, config.CONVERSATIONS_DIR)
    
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404
    
    return jsonify(conversation)









/* Add these styles to your style.css file */

/* Comparison page specific styles */
.preview-message {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.preview-badge {
  flex-shrink: 0;
  font-size: 0.75rem;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  color: white;
  text-transform: capitalize;
}

.preview-content {
  background-color: white;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  flex-grow: 1;
  font-size: 0.9rem;
  box-shadow: var(--shadow-sm);
}

.conversation-preview {
  max-height: 300px;
  overflow-y: auto;
  background-color: var(--gray-50);
  border-radius: var(--border-radius);
  padding: 1rem;
  border: 1px solid var(--gray-200);
}

.comparison-result {
  padding: 1rem;
}

.comparison-result h3, .comparison-result h4, .comparison-result h5 {
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
  color: var(--gray-800);
}

.comparison-result ul, .comparison-result ol {
  margin-bottom: 1.5rem;
  padding-left: 1.5rem;
}

.comparison-result li {
  margin-bottom: 0.5rem;
}

.comparison-result p {
  margin-bottom: 1rem;
  line-height: 1.7;
}

.comparison-result code {
  background-color: var(--gray-100);
  padding: 0.2rem 0.4rem;
  border-radius: 0.25rem;
  font-family: 'JetBrains Mono', 'Fira Code', 'Roboto Mono', 'Courier New', monospace;
  font-size: 0.9rem;
  color: var(--primary-dark);
}

.comparison-result pre {
  background-color: var(--gray-900);
  color: white;
  padding: 1rem;
  border-radius: var(--border-radius);
  overflow-x: auto;
  margin: 1rem 0;
}

.comparison-result table {
  width: 100%;
  margin-bottom: 1.5rem;
  border-collapse: collapse;
}

.comparison-result th, .comparison-result td {
  padding: 0.75rem;
  border: 1px solid var(--gray-300);
}

.comparison-result th {
  background-color: var(--gray-100);
  font-weight: 600;
}

.comparison-result tr:nth-child(even) {
  background-color: var(--gray-50);
}





