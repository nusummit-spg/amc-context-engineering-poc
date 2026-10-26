import { useState, useEffect } from "react";
import { Plus, Trash2, Database, RefreshCw } from "lucide-react";
import DataFrame from "../../components/widgets/DataFrame";
import Divider from "../../components/widgets/Divider";
import TextInput from "../../components/widgets/TextInput";
import Selectbox from "../../components/widgets/Selectbox";
import Button from "../../components/widgets/Button";
import Alert from "../../components/widgets/Alert";
import { AMCRole } from "../../data/rbac";
import { useAppState } from "../../state/AppState";

export default function AdminUsersTab() {
  const {
    users,
    saveUserProfile,
    deleteUserProfile,
    activeUser,
    activeUsername,
    authedUsername,
    refreshUsers,
    isUsersSyncing,
  } = useAppState();

  const currentAdmin = (authedUsername || activeUsername || activeUser?.username || "").trim();
  const normalize = (s) => (s || "").trim().toLowerCase().replace(".", "_");
  const isSelf = (uname) => {
    if (!currentAdmin || !uname) return false;
    return normalize(uname) === normalize(currentAdmin);
  };

  // Re-sync with backend (data.db auth_users) on tab mount
  useEffect(() => {
    if (typeof refreshUsers === "function") {
      refreshUsers();
    }
  }, [refreshUsers]);

  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(Object.values(AMCRole)[0]);
  const [department, setDepartment] = useState("");
  const [password, setPassword] = useState("");
  const [formMsg, setFormMsg] = useState(null);

  // System-protected users that cannot be removed
  const protectedUsernames = ["sarah_compliance", "sarah.compliance", "compliance_officer", "admin", "amc_admin", "amc_auditor", "amc_researcher"];
  const isProtectedUser = (uname) => {
    const norm = normalize(uname);
    return isSelf(uname) || protectedUsernames.some((p) => normalize(p) === norm);
  };

  // Filter out system-protected default users AND the currently logged in administrator's account
  const removableUsers = users.filter((u) => !isProtectedUser(u.username));

  const [delUser, setDelUser] = useState(removableUsers[0]?.username || "");
  const [delMsg, setDelMsg] = useState(null);

  useEffect(() => {
    if (removableUsers.length > 0 && !removableUsers.some((u) => u.username === delUser)) {
      setDelUser(removableUsers[0]?.username || "");
    } else if (removableUsers.length === 0 && delUser) {
      setDelUser("");
    }
  }, [removableUsers, delUser]);

  const handleSave = async () => {
    if (username && fullName) {
      const userPayload = {
        username: username.trim().toLowerCase(),
        full_name: fullName.trim(),
        role,
        department: department.trim() || "General",
        email: email.trim() || `${username.trim().toLowerCase()}@amc.com`,
        status: "Active",
        password: password.trim() || undefined,
      };

      try {
        const resp = await saveUserProfile(userPayload);
        const assignedPwd = resp?.assigned_password || password.trim() || "Welcome@2026";
        setFormMsg({
          type: "success",
          text: `User profile '${username.trim().toLowerCase()}' successfully saved and synchronized with data.db auth users! Login password: '${assignedPwd}'. The user can now log in using these credentials.`,
        });
        setUsername("");
        setFullName("");
        setEmail("");
        setDepartment("");
        setPassword("");
      } catch (err) {
        setFormMsg({ type: "error", text: err?.message || "Failed to save user profile." });
      }
    } else {
      setFormMsg({ type: "error", text: "Please fill in both Username and Full Name." });
    }
  };

  const handleDelete = async () => {
    if (!delUser) return;
    if (isSelf(delUser)) {
      setDelMsg({ type: "error", text: "Administrators cannot delete their own account." });
      return;
    }
    try {
      await deleteUserProfile(delUser);
      setDelMsg({ type: "success", text: `User profile '${delUser}' removed and synchronized with data.db auth users.` });
    } catch (err) {
      setDelMsg({ type: "error", text: err?.message || `Failed to remove user '${delUser}'.` });
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
        <div>
          <h3 className="stSubheader" style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
            <Database size={18} style={{ color: "var(--color-navy-700, #1e3a8a)" }} />
            Active User Profiles
          </h3>
          <div style={{ fontSize: "0.82rem", color: "var(--text-muted, #64748b)", marginTop: 4 }}>
            Synchronized with <code style={{ fontSize: "0.78rem" }}>data.db</code> auth users ({users.length} active profiles)
          </div>
        </div>
        <button
          type="button"
          onClick={() => refreshUsers && refreshUsers()}
          disabled={isUsersSyncing}
          className="stButton"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "5px 12px",
            fontSize: "0.82rem",
            fontWeight: 500,
            cursor: isUsersSyncing ? "wait" : "pointer",
            borderRadius: 6,
            border: "1px solid var(--border-color, #cbd5e1)",
            backgroundColor: "transparent",
            color: "var(--text-color, #1e293b)",
          }}
          title="Re-sync active user profiles from data.db auth_users"
        >
          <RefreshCw size={13} style={{ animation: isUsersSyncing ? "st-spin 0.7s linear infinite" : "none" }} />
          {isUsersSyncing ? "Syncing..." : "Sync with Database"}
        </button>
      </div>
      <DataFrame
        columns={["username", "full_name", "role", "department", "email", "status"]}
        rows={users}
      />

      <Divider />
      <h3 className="stSubheader">
        <Plus size={17} strokeWidth={1.75} style={{ marginRight: 6, verticalAlign: "-3px" }} />
        Create / Update User Profile
      </h3>
      <div className="stForm">
        <div className="stFormRow">
          <div>
            <TextInput label="Username" value={username} onChange={setUsername} placeholder="e.g. j_doe_compliance" />
            <div style={{ height: 10 }} />
            <TextInput label="Full Name" value={fullName} onChange={setFullName} placeholder="e.g. Jane Doe" />
            <div style={{ height: 10 }} />
            <TextInput label="Email Address" value={email} onChange={setEmail} placeholder="jane.doe@amc.com" />
          </div>
          <div>
            <Selectbox
              label="Assign AMC Organizational Role"
              options={Object.values(AMCRole)}
              value={role}
              onChange={setRole}
            />
            <div style={{ height: 10 }} />
            <TextInput label="Department / Unit" value={department} onChange={setDepartment} placeholder="e.g. Legal & Compliance" />
            <div style={{ height: 10 }} />
            <TextInput
              label="Account Password"
              type="password"
              value={password}
              onChange={setPassword}
              placeholder="Leave blank for default: Welcome@2026"
            />
          </div>
        </div>
        <div style={{ marginTop: 12, maxWidth: 220 }}>
          <Button kind="primary" fullWidth onClick={handleSave}>Save User Profile</Button>
        </div>
        {formMsg && (
          <div style={{ marginTop: 10 }}>
            <Alert type={formMsg.type}>{formMsg.text}</Alert>
          </div>
        )}
      </div>

      <Divider />
      <h3 className="stSubheader">
        <Trash2 size={16} strokeWidth={1.75} style={{ marginRight: 6, verticalAlign: "-3px" }} />
        Remove User Profile
      </h3>
      {currentAdmin && (
        <div style={{ fontSize: "0.82rem", color: "var(--text-muted, #64748b)", marginBottom: 10 }}>
          Self-deletion protection: Your active account (<strong>{currentAdmin}</strong>) cannot be deleted.
        </div>
      )}
      {removableUsers.length > 0 ? (
        <>
          <Selectbox
            label="Select User to Remove"
            options={removableUsers.map((u) => u.username)}
            value={delUser}
            onChange={setDelUser}
          />
          <div style={{ marginTop: 10, maxWidth: 220 }}>
            <Button
              kind="danger"
              fullWidth
              onClick={handleDelete}
              disabled={!delUser || isSelf(delUser)}
            >
              Delete Selected Profile
            </Button>
          </div>
        </>
      ) : (
        <div style={{ padding: "12px 14px", backgroundColor: "rgba(100, 116, 139, 0.08)", borderRadius: 6, fontSize: "0.88rem", color: "var(--text-muted, #64748b)" }}>
          No other user profiles are eligible for removal.
        </div>
      )}
      {delMsg && (
        <div style={{ marginTop: 10 }}>
          <Alert type={typeof delMsg === "object" ? delMsg.type : "success"}>
            {typeof delMsg === "object" ? delMsg.text : delMsg}
          </Alert>
        </div>
      )}
    </div>
  );
}
