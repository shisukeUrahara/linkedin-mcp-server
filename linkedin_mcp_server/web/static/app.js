import React, { useCallback, useEffect, useMemo, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";

const SESSION_STORAGE_KEY = "linkedin-mcp-session-token";
const API_BASE = window.__LINKEDIN_MCP_API_BASE__ || "";

const initialMessages = [
  {
    id: "welcome",
    role: "system",
    author: "Welcome",
    content:
      "Create a LinkedIn session and start chatting with the agent for personalised insights.",
  },
];

function classNames(...values) {
  return values.filter(Boolean).join(" ");
}

function uniqueId(prefix = "id") {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function useSessionToken() {
  const [token, setToken] = useState(() => {
    try {
      const persisted = window.localStorage.getItem(SESSION_STORAGE_KEY);
      if (persisted) {
        return persisted;
      }
      const injected = window.__LINKEDIN_MCP_SESSION_TOKEN__ || "";
      if (injected) {
        window.localStorage.setItem(SESSION_STORAGE_KEY, injected);
        return injected;
      }
      return "";
    } catch (error) {
      console.warn("Unable to read session token", error);
      return "";
    }
  });

  const updateToken = useCallback((value) => {
    setToken(value || "");
    try {
      if (value) {
        window.localStorage.setItem(SESSION_STORAGE_KEY, value);
        window.__LINKEDIN_MCP_SESSION_TOKEN__ = value;
      } else {
        window.localStorage.removeItem(SESSION_STORAGE_KEY);
        window.__LINKEDIN_MCP_SESSION_TOKEN__ = "";
      }
    } catch (error) {
      console.warn("Unable to persist session token", error);
    }
  }, []);

  return [token, updateToken];
}

async function jsonRequest(path, options = {}) {
  let response;
  try {
    const { headers: overrideHeaders, ...rest } = options;
    const headers = { "Content-Type": "application/json", ...(overrideHeaders || {}) };
    response = await fetch(`${API_BASE}${path}`, {
      ...rest,
      headers,
    });
  } catch (networkError) {
    const error = new Error(networkError.message || "Network request failed");
    error.cause = networkError;
    throw error;
  }

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.detail || payload?.message || "Request failed";
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function TabButton({ active, onClick, children }) {
  return (
    <button className={classNames("tab", active && "active")} onClick={onClick} type="button">
      {children}
    </button>
  );
}

function Message({ message }) {
  return (
    <div className={classNames("chat-message", message.role, message.kind && `kind-${message.kind}`)}>
      <div className="meta">{message.author}</div>
      <div className="content">{message.content}</div>
    </div>
  );
}

function SessionCard({ sessionToken, onTokenChange, onMessage }) {
  const [activeTab, setActiveTab] = useState("cookie");
  const [cookie, setCookie] = useState("");
  const [validateCookie, setValidateCookie] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const handleCookieSubmit = useCallback(
    async (event) => {
      event.preventDefault();
      if (!cookie) return;
      setBusy(true);
      try {
        const payload = await jsonRequest("/api/sessions/cookie", {
          method: "POST",
          body: JSON.stringify({ cookie, validate_cookie: validateCookie }),
        });
        onTokenChange(payload.session_token || "");
        setCookie("");
        setValidateCookie(false);
        onMessage({
          role: "system",
          author: "Session ready",
          content: "You're connected. Ask the agent for insights whenever you're ready.",
          kind: "success",
        });
      } catch (error) {
        onMessage({
          role: "system",
          author: "Cookie error",
          content: error.message,
          kind: "error",
        });
      } finally {
        setBusy(false);
      }
    },
    [cookie, onMessage, onTokenChange, validateCookie],
  );

  const handleCredentialSubmit = useCallback(
    async (event) => {
      event.preventDefault();
      if (!email || !password) return;
      setBusy(true);
      try {
        const payload = await jsonRequest("/api/sessions/credentials", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        onTokenChange(payload.session_token || "");
        onMessage({
          role: "system",
          author: "Session ready",
          content: "Login successful. Start a chat to explore your LinkedIn data.",
          kind: "success",
        });
        setPassword("");
        setEmail("");
      } catch (error) {
        onMessage({
          role: "system",
          author: "Login error",
          content: error.message,
          kind: "error",
        });
      } finally {
        setBusy(false);
      }
    },
    [email, password, onMessage, onTokenChange],
  );

  const handleClearSession = useCallback(async () => {
    if (!sessionToken) return;
    try {
      await jsonRequest(`/api/sessions/${sessionToken}`, { method: "DELETE" });
    } catch (error) {
      console.warn("Unable to clear remote session", error);
    }
    onTokenChange("");
    onMessage({
      role: "system",
      author: "Session cleared",
      content: "Removed the saved session. Create a new one when you're ready.",
      kind: "info",
    });
  }, [onMessage, onTokenChange, sessionToken]);

  const handleCopy = useCallback(async () => {
    if (!sessionToken) return;
    try {
      await navigator.clipboard.writeText(sessionToken);
      onMessage({
        role: "system",
        author: "Copied",
        content: "Session token copied to clipboard.",
        kind: "success",
      });
    } catch (error) {
      onMessage({
        role: "system",
        author: "Clipboard error",
        content: error.message,
        kind: "error",
      });
    }
  }, [onMessage, sessionToken]);

  return (
    <section className="card" id="session-card">
      <h2>1. Create a LinkedIn Session</h2>
      <p>
        Provide either your <code>li_at</code> cookie or your LinkedIn credentials. A unique session
        token will be generated and stored only in your browser.
      </p>

      <div className="form-tabs">
        <TabButton active={activeTab === "cookie"} onClick={() => setActiveTab("cookie")}>
          Use Cookie
        </TabButton>
        <TabButton active={activeTab === "credentials"} onClick={() => setActiveTab("credentials")}>
          Use Credentials
        </TabButton>
      </div>

      {activeTab === "cookie" ? (
        <form className="form" onSubmit={handleCookieSubmit}>
          <label>
            LinkedIn Cookie (li_at value)
            <input
              autoComplete="off"
              onChange={(event) => setCookie(event.target.value)}
              placeholder="li_at=..."
              required
              type="text"
              value={cookie}
            />
          </label>
          <label className="checkbox">
            <input
              checked={validateCookie}
              onChange={(event) => setValidateCookie(event.target.checked)}
              type="checkbox"
            />
            Validate cookie before saving
          </label>
          <button disabled={busy} type="submit">
            {busy ? "Saving..." : "Save Session"}
          </button>
        </form>
      ) : (
        <form className="form" onSubmit={handleCredentialSubmit}>
          <label>
            Email
            <input
              autoComplete="email"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </label>
          <label>
            Password
            <input
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>
          <button disabled={busy} type="submit">
            {busy ? "Signing in..." : "Login & Save Session"}
          </button>
        </form>
      )}

      {sessionToken ? (
        <div className="session-info">
          <p>
            <strong>Current session token:</strong> <code>{sessionToken}</code>
          </p>
          <div className="session-actions">
            <button onClick={handleCopy} type="button">
              Copy Token
            </button>
            <button className="danger" onClick={handleClearSession} type="button">
              Clear Session
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function ChatCard({ sessionToken, onMessage }) {
  const [messages, setMessages] = useState(initialMessages);
  const [inputValue, setInputValue] = useState("");
  const [busy, setBusy] = useState(false);

  const pushMessage = useCallback((entry) => {
    setMessages((previous) => [...previous, { id: uniqueId("chat"), ...entry }]);
  }, []);

  useEffect(() => {
    setMessages([...initialMessages]);
  }, [sessionToken]);

  useEffect(() => {
    if (!sessionToken) {
      pushMessage({
        role: "system",
        author: "Session required",
        content: "Create a LinkedIn session to enable the chat agent.",
        kind: "info",
      });
    }
  }, [pushMessage, sessionToken]);

  const handleSubmit = useCallback(
    async (event) => {
      event.preventDefault();
      const text = inputValue.trim();
      if (!text) return;
      if (!sessionToken) {
        onMessage({
          role: "system",
          author: "Missing session",
          content: "Create a LinkedIn session first.",
          kind: "error",
        });
        return;
      }

      pushMessage({ role: "user", author: "You", content: text });
      setInputValue("");
      setBusy(true);
      try {
        const payload = await jsonRequest("/api/chat", {
          method: "POST",
          body: JSON.stringify({ session_token: sessionToken, message: text }),
        });
        pushMessage({ role: "assistant", author: "Agent", content: payload.reply });
      } catch (error) {
        onMessage({
          role: "system",
          author: "Agent error",
          content: error.message,
          kind: "error",
        });
      } finally {
        setBusy(false);
      }
    },
    [inputValue, onMessage, pushMessage, sessionToken],
  );

  const combinedMessages = useMemo(() => messages, [messages]);

  return (
    <section className="card" id="chat-card">
      <h2>2. Chat with the Agent</h2>
      <div className="chat-window">
        {combinedMessages.map((message) => (
          <Message key={message.id} message={message} />
        ))}
      </div>
      <form className="chat-input" onSubmit={handleSubmit}>
        <input
          autoComplete="off"
          onChange={(event) => setInputValue(event.target.value)}
          placeholder="Ask for recommended jobs or paste a LinkedIn link..."
          value={inputValue}
        />
        <button disabled={busy} type="submit">
          {busy ? "Sending..." : "Send"}
        </button>
      </form>
    </section>
  );
}

function TipsCard() {
  return (
    <section className="card" id="help-card">
      <h2>Tips</h2>
      <ul>
        <li>Ask for "recommended jobs" to fetch LinkedIn suggestions.</li>
        <li>Paste a profile, job, or company URL to get a quick summary.</li>
        <li>Your session token lives only in this browser tab and keeps your LinkedIn data isolated.</li>
      </ul>
    </section>
  );
}

function App() {
  const [sessionToken, setSessionToken] = useSessionToken();
  const [events, setEvents] = useState([]);

  const pushEvent = useCallback((entry) => {
    setEvents((previous) => {
      const next = [...previous.slice(-4), { id: uniqueId("event"), ...entry }];
      return next;
    });
  }, []);

  return (
    <div className="page">
      <header>
        <h1>LinkedIn MCP Companion</h1>
        <p className="subtitle">
          Sign in with your LinkedIn account and chat with an agent that uses your MCP tools.
        </p>
      </header>
      <main className="layout">
        <div className="column column-primary">
          <SessionCard onMessage={pushEvent} onTokenChange={setSessionToken} sessionToken={sessionToken} />
          <TipsCard />
        </div>
        <div className="column column-chat">
          <ChatCard onMessage={pushEvent} sessionToken={sessionToken} />
        </div>
      </main>
      {events.length > 0 ? (
        <div className="event-feed" role="status">
          {events.map((event) => (
            <Message key={event.id} message={event} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

const container = document.getElementById("root");
if (!container) {
  throw new Error("Missing root element for React application");
}

createRoot(container).render(<App />);
