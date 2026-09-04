import { useState } from "react";
import DataFrame from "../../components/widgets/DataFrame";
import Divider from "../../components/widgets/Divider";
import TextInput from "../../components/widgets/TextInput";
import Selectbox from "../../components/widgets/Selectbox";
import Button from "../../components/widgets/Button";
import Alert from "../../components/widgets/Alert";
import { AMCRole } from "../../data/rbac";
import { useAppState } from "../../state/AppState";

export default function AdminUsersTab() {
  const { users, saveUserProfile, deleteUserProfile } = useAppState();

  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(Object.values(AMCRole)[0]);
  const [department, setDepartment] = useState("");
  const [formMsg, setFormMsg] = useState(null);

  const [delUser, setDelUser] = useState(
    users.find((u) => u.username !== "sarah_compliance")?.username || ""
  );
  const [delMsg, setDelMsg] = useState(null);

  const removableUsers = users.filter((u) => u.username !== "sarah_compliance");

  const handleSave = async () => {
    if (username && fullName) {
      const userPayload = {
        username: username.trim().toLowerCase(),
        full_name: fullName.trim(),
        role,
        department: department.trim() || "General",
        email: email.trim() || `${username.trim().toLowerCase()}@amc.com`,
        status: "Active",
      };

      await saveUserProfile(userPayload);

      setFormMsg({ type: "success", text: `User profile '${username}' (${role}) successfully created/updated!` });
      setUsername(""); setFullName(""); setEmail(""); setDepartment("");
    } else {
      setFormMsg({ type: "error", text: "Please fill in both Username and Full Name." });
    }
  };

  const handleDelete = async () => {
    if (!delUser) return;
    await deleteUserProfile(delUser);
    setDelMsg(`User profile '${delUser}' removed.`);
  };

  return (
    <div>
      <h3 className="stSubheader">Active User Profiles</h3>
      <DataFrame
        columns={["username", "full_name", "role", "department", "email", "status"]}
        rows={users}
      />

      <Divider />
      <h3 className="stSubheader">➕ Create / Update User Profile</h3>
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
      <h3 className="stSubheader">❌ Remove User Profile</h3>
      <Selectbox
        label="Select User to Remove"
        options={removableUsers.map((u) => u.username)}
        value={delUser}
        onChange={setDelUser}
      />
      <div style={{ marginTop: 10, maxWidth: 220 }}>
        <Button kind="secondary" fullWidth onClick={handleDelete}>Delete Selected Profile</Button>
      </div>
      {delMsg && (
        <div style={{ marginTop: 10 }}>
          <Alert type="success">{delMsg}</Alert>
        </div>
      )}
    </div>
  );
}
