import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { AMCRole, ROLE_PERMISSIONS } from "./src/data/rbac.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

console.log("=== Running Authentication & RBAC Verification Tests ===");

// 1. Verify users.json structure
const usersRaw = fs.readFileSync(path.join(__dirname, "src/data/users.json"), "utf8");
const users = JSON.parse(usersRaw);

assert.strictEqual(users.length, 5, "Must contain exactly 5 predefined operator accounts");

const expectedAccounts = [
  {
    username: "sarah.compliance",
    password: "Compliance@2026",
    role: AMCRole.COMPLIANCE_OFFICER,
    canAdmin: true,
    canCompare: true,
  },
  {
    username: "vikram.pm",
    password: "Portfolio@2026",
    role: AMCRole.FUND_MANAGER,
    canAdmin: false,
    canCompare: true,
  },
  {
    username: "ananya.esg",
    password: "Sustainability@2026",
    role: AMCRole.ESG_ANALYST,
    canAdmin: false,
    canCompare: true,
  },
  {
    username: "rahul.sales",
    password: "Distribution@2026",
    role: AMCRole.SALES_MANAGER,
    canAdmin: false,
    canCompare: false,
  },
  {
    username: "priya.investor",
    password: "Investor@2026",
    role: AMCRole.RETAIL_INVESTOR,
    canAdmin: false,
    canCompare: false,
  },
];

expectedAccounts.forEach((expected) => {
  const account = users.find((u) => u.username === expected.username);
  assert.ok(account, `Account ${expected.username} must exist in users.json`);
  assert.strictEqual(account.password, expected.password, `Password for ${expected.username} matches`);
  assert.strictEqual(account.role, expected.role, `Role for ${expected.username} matches ${expected.role}`);
  assert.ok(account.display_name, `Display name must be present for ${expected.username}`);
  assert.ok(account.avatar_initials, `Avatar initials must be present for ${expected.username}`);

  // Test permissions mapped through ROLE_PERMISSIONS
  const perms = ROLE_PERMISSIONS[account.role];
  assert.ok(perms, `Role permissions must exist for ${account.role}`);
  assert.strictEqual(Boolean(perms.can_view_admin_panel), expected.canAdmin, `can_view_admin_panel for ${account.role}`);
  assert.strictEqual(Boolean(perms.can_access_compare_tab), expected.canCompare, `can_access_compare_tab for ${account.role}`);
  console.log(`✓ Account verified: ${account.username} (${account.display_name}) -> Role: ${account.role}`);
});

// 2. Test Login Logic Simulation
function simulateLogin(inputUserId, inputPassword) {
  const clean = (inputUserId || "").trim().toLowerCase();
  const matched = users.find((u) => u.username.toLowerCase() === clean);
  if (!matched || matched.password !== inputPassword) {
    return { success: false, error: "That User ID or password doesn't match our records." };
  }
  return { success: true, user: matched };
}

// Positive tests
assert.strictEqual(simulateLogin("sarah.compliance", "Compliance@2026").success, true);
assert.strictEqual(simulateLogin("  SARAH.COMPLIANCE  ", "Compliance@2026").success, true, "Case-insensitive username with whitespace");
assert.strictEqual(simulateLogin("vikram.pm", "Portfolio@2026").success, true);
assert.strictEqual(simulateLogin("ananya.esg", "Sustainability@2026").success, true);
assert.strictEqual(simulateLogin("rahul.sales", "Distribution@2026").success, true);
assert.strictEqual(simulateLogin("priya.investor", "Investor@2026").success, true);

// Negative tests
assert.strictEqual(simulateLogin("sarah.compliance", "WrongPassword!").success, false);
assert.strictEqual(simulateLogin("unknown.user", "Compliance@2026").success, false);
assert.strictEqual(simulateLogin("", "Compliance@2026").success, false);
assert.strictEqual(simulateLogin("sarah.compliance", "").success, false);
assert.strictEqual(simulateLogin("", "").success, false);

console.log("✓ Login credential validation tests passed!");

// 3. Storage and Session Simulation
const storage = {};
function setStorage(k, v) { storage[k] = JSON.stringify(v); }
function getStorage(k, fb) { return storage[k] ? JSON.parse(storage[k]) : fb; }

// Initial state: not authenticated
let session = getStorage("ns_cg_auth_session_v1", { isAuthenticated: false, authedUsername: null });
assert.strictEqual(session.isAuthenticated, false);
assert.strictEqual(session.authedUsername, null);

// Perform login
const loginRes = simulateLogin("sarah.compliance", "Compliance@2026");
if (loginRes.success) {
  setStorage("ns_cg_auth_session_v1", { isAuthenticated: true, authedUsername: loginRes.user.username });
  setStorage("ns_cg_active_user_v1", loginRes.user.username);
}

session = getStorage("ns_cg_auth_session_v1", null);
assert.strictEqual(session.isAuthenticated, true);
assert.strictEqual(session.authedUsername, "sarah.compliance");
assert.strictEqual(getStorage("ns_cg_active_user_v1", null), "sarah.compliance");
console.log("✓ Session persistence simulation passed!");

// Perform logout
setStorage("ns_cg_auth_session_v1", { isAuthenticated: false, authedUsername: null });
session = getStorage("ns_cg_auth_session_v1", null);
assert.strictEqual(session.isAuthenticated, false);
assert.strictEqual(session.authedUsername, null);
console.log("✓ Session logout simulation passed!");

console.log("\nALL AUTHENTICATION & RBAC TESTS PASSED SUCCESSFULLY! 🚀");
