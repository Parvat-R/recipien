import { useState, useRef, useEffect } from "react";

const API_BASE = "http://localhost:8000";

function getThreadId() {
  let id = sessionStorage.getItem("thread_id");
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem("thread_id", id);
  }
  return id;
}

function stripHtmlFences(text) {
  return text
    .replace(/^```html\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
}

function isHtml(text) {
  return /<[a-z][\s\S]*>/i.test(text.trim());
}

function Message({ msg }) {
  const isUser = msg.role === "user";
  const content = msg.content ? stripHtmlFences(msg.content) : "";
  const renderAsHtml = !isUser && content && isHtml(content);

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: isUser ? "flex-end" : "flex-start",
      marginBottom: "1.25rem",
      gap: "6px",
    }}>
      <span style={{
        fontSize: "11px",
        color: "#888",
        fontFamily: "'DM Mono', monospace",
        letterSpacing: "0.05em",
        textTransform: "uppercase",
      }}>
        {isUser ? "you" : "recipien"}
      </span>

      {msg.image && (
        <img
          src={msg.image}
          alt="uploaded"
          style={{
            maxWidth: "220px",
            borderRadius: "12px",
            border: "1px solid #e5e5e5",
          }}
        />
      )}

      <div style={{
        maxWidth: renderAsHtml ? "90%" : "75%",
        width: renderAsHtml ? "90%" : undefined,
        padding: "16px 20px",
        borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
        background: isUser ? "#1a1a1a" : "#f5f3ef",
        color: isUser ? "#fafafa" : "#1a1a1a",
        fontSize: "15px",
        lineHeight: "1.65",
        fontFamily: "'Lora', serif",
        whiteSpace: renderAsHtml ? "normal" : "pre-wrap",
        wordBreak: "break-word",
      }}>
        {!content ? (
          <span style={{ opacity: 0.4, fontStyle: "italic" }}>thinking...</span>
        ) : renderAsHtml ? (
          <div
            className="recipe-html"
            dangerouslySetInnerHTML={{ __html: content }}
          />
        ) : (
          content
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [image, setImage] = useState(null);      // { file, previewUrl }
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);
  const fileRef = useRef(null);
  const threadId = useRef(getThreadId());

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text && !image) return;

    const userMsg = {
      role: "user",
      content: text,
      image: image?.previewUrl || null,
    };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    // placeholder for assistant streaming
    const assistantIdx = messages.length + 1;
    setMessages(prev => [...prev, { role: "assistant", content: "" }]);

    try {
      const form = new FormData();
      form.append("prompt", text);
      form.append("thread_id", threadId.current);
      if (image?.file) form.append("image", image.file);

      const res = await fetch(`${API_BASE}/chat`, { method: "POST", body: form });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        accumulated += decoder.decode(value, { stream: true });
        const snapshot = accumulated;
        setMessages(prev =>
          prev.map((m, i) =>
            i === assistantIdx ? { ...m, content: snapshot } : m
          )
        );
      }
    } catch (err) {
      setMessages(prev =>
        prev.map((m, i) =>
          i === assistantIdx
            ? { ...m, content: `Error: ${err.message}` }
            : m
        )
      );
    } finally {
      setLoading(false);
      setImage(null);
    }
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  function handleFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    setImage({ file, previewUrl: URL.createObjectURL(file) });
    e.target.value = "";
  }

  function removeImage() {
    if (image?.previewUrl) URL.revokeObjectURL(image.previewUrl);
    setImage(null);
  }

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;1,400&family=DM+Mono:wght@400;500&display=swap');

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        body {
          background: #faf9f7;
          font-family: 'Lora', serif;
        }

        #root {
          border-inline: none;
        }

        .chat-root {
          display: flex;
          flex-direction: column;
          height: 100vh;
          max-width: 720px;
          margin: 0 auto;
        }

        .chat-header {
          padding: 1.5rem 1.5rem 1rem;
          border-bottom: 1px solid #ebebeb;
          background: #faf9f7;
        }

        .chat-header h1 {
          font-family: 'Lora', serif;
          font-size: 22px;
          font-weight: 500;
          color: #1a1a1a;
          letter-spacing: -0.02em;
        }

        .chat-header p {
          font-family: 'DM Mono', monospace;
          font-size: 11px;
          color: #999;
          margin-top: 3px;
          letter-spacing: 0.04em;
        }

        .chat-messages {
          flex: 1;
          overflow-y: auto;
          padding: 1.5rem;
          scroll-behavior: smooth;
        }

        .chat-empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100%;
          gap: 12px;
          color: #bbb;
          font-family: 'DM Mono', monospace;
          font-size: 12px;
          text-align: center;
          line-height: 1.7;
        }

        .chat-empty-icon {
          font-size: 36px;
          filter: grayscale(1) opacity(0.4);
        }

        .chat-input-area {
          padding: 1rem 1.5rem 1.5rem;
          border-top: 1px solid #ebebeb;
          background: #faf9f7;
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .chat-input-inner {
          width: 70%;
          min-width: 800px;
        }

        .image-preview {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 10px;
          padding: 8px 10px;
          background: #f0eeea;
          border-radius: 10px;
          width: fit-content;
        }

        .image-preview img {
          width: 44px;
          height: 44px;
          border-radius: 6px;
          object-fit: cover;
        }

        .image-preview span {
          font-family: 'DM Mono', monospace;
          font-size: 11px;
          color: #666;
          max-width: 140px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .image-preview button {
          background: none;
          border: none;
          cursor: pointer;
          color: #999;
          font-size: 16px;
          line-height: 1;
          padding: 2px;
        }

        .input-row {
          display: flex;
          align-items: center;
          gap: 8px;
          background: #fff;
          border: 1px solid #e0deda;
          border-radius: 14px;
          padding: 8px 8px 8px 14px;
          min-width: 800px;
        }

        .input-row textarea {
          flex: 1;
          border: none;
          outline: none;
          resize: none;
          font-family: 'Lora', serif;
          font-size: 15px;
          line-height: 1.55;
          color: #1a1a1a;
          background: transparent;
          min-height: 24px;
          max-height: 160px;
          overflow-y: auto;
        }

        .input-row textarea::placeholder {
          color: #bbb;
          font-style: italic;
        }

        .icon-btn {
          background: none;
          border: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 36px;
          height: 36px;
          border-radius: 8px;
          color: #999;
          transition: background 0.15s, color 0.15s;
          flex-shrink: 0;
        }

        .icon-btn:hover { background: #f0eeea; color: #555; }

        .send-btn {
          background: #1a1a1a;
          border: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 36px;
          height: 36px;
          border-radius: 8px;
          color: #fff;
          flex-shrink: 0;
          transition: opacity 0.15s;
        }

        .send-btn:disabled { opacity: 0.35; cursor: not-allowed; }
        .send-btn:not(:disabled):hover { opacity: 0.8; }

        .recipe-html .recipe-container { display: flex; flex-direction: column; gap: 1.25rem; }
        .recipe-html .featured-recipe { background: #fff; border: 1px solid #e0deda; border-radius: 14px; padding: 1.25rem 1.5rem; text-align: justify;}
        .recipe-html .featured-recipe h2 { color: #000; font-size: 17px; font-weight: 500; margin-bottom: 0.5rem; }
        .recipe-html .featured-recipe h3 { font-size: 14px; font-weight: 500; margin: 1rem 0 0.4rem; color: #555; text-transform: uppercase; letter-spacing: 0.05em; font-family: 'DM Mono', monospace; }
        .recipe-html .featured-recipe ul, .recipe-html .featured-recipe ol { padding-left: 1.25rem; margin: 0; }
        .recipe-html .featured-recipe li { margin-bottom: 0.3rem; font-size: 14px; line-height: 1.6; }
        .recipe-html .featured-recipe p { font-size: 14px; margin: 0.3rem 0; }
        .recipe-html .featured-recipe a { color: #1a1a1a; font-size: 13px; font-family: 'DM Mono', monospace; }
        .recipe-html .other-recommendations { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
        .recipe-html .other-recommendations h2 { grid-column: 1 / -1; font-size: 13px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; color: #888; font-family: 'DM Mono', monospace; margin-bottom: 2px; }
        .recipe-html .recipe-card { background: #fff; border: 1px solid #e0deda; border-radius: 12px; padding: 1rem; }
        .recipe-html .recipe-card h3 { font-size: 14px; font-weight: 500; margin-bottom: 6px; }
        .recipe-html .recipe-card p { font-size: 13px; color: #666; margin: 3px 0; line-height: 1.5; }
        .recipe-html .recipe-card a { font-size: 12px; font-family: 'DM Mono', monospace; color: #1a1a1a; margin-top: 8px; display: inline-block; }
        .chat-messages {
          scrollbar-color: #aba8a2 #faf9f7; /* thumb color, track color */
          scrollbar-width: thin; /* can be auto, thin, or none */
        }
      
        .chat-messages {
          scrollbar-color: #aba8a2 #faf9f7; /* thumb color, track color */
          scrollbar-width: thin; /* can be auto, thin, or none */
        }
      
      `}</style>

      <div className="chat-root">
        <div className="chat-header">
          <h1>Recipien</h1>
          <p>your ai recipe assistant</p>
        </div>

        <div className="chat-messages">
          {messages.length === 0 ? (
            <div className="chat-empty">
              <span className="chat-empty-icon">🍳</span>
              <span>Tell me what ingredients you have,<br />or upload a photo of your fridge.</span>
            </div>
          ) : (
            messages.map((msg, i) => <Message key={i} msg={msg} />)
          )}
          <div ref={bottomRef} />
        </div>

        <div className="chat-input-area">
          <div className="chat-input-inner">
          {image && (
            <div className="image-preview">
              <img src={image.previewUrl} alt="preview" />
              <span>{image.file.name}</span>
              <button onClick={removeImage} title="Remove">✕</button>
            </div>
          )}

          <div className="input-row">
            <textarea
              rows={1}
              placeholder="What ingredients do you have?"
              value={input}
              onChange={e => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = e.target.scrollHeight + "px";
              }}
              onKeyDown={handleKey}
              disabled={loading}
            />

            <button
              className="icon-btn"
              title="Attach image"
              onClick={() => fileRef.current.click()}
              disabled={loading}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="3"/>
                <circle cx="8.5" cy="8.5" r="1.5"/>
                <polyline points="21 15 16 10 5 21"/>
              </svg>
            </button>

            <button
              className="send-btn"
              onClick={send}
              disabled={loading || (!input.trim() && !image)}
              title="Send"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </div>

          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            style={{ display: "none" }}
            onChange={handleFile}
          />
          </div>
        </div>
      </div>
    </>
  );
}