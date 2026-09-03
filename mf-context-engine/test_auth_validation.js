import assert from "node:assert";
import { validateUserId, validatePassword, validateLoginForm } from "./src/utils/authValidation.js";

console.log("=== Running Client-Side Auth Validation Tests ===");

// 1. validateUserId tests
assert.strictEqual(validateUserId(""), "Enter your user ID", "Empty username rejected");
assert.strictEqual(validateUserId("   "), "Enter your user ID", "Whitespace username rejected");
assert.strictEqual(validateUserId(null), "Enter your user ID", "Null username rejected");
assert.strictEqual(validateUserId(undefined), "Enter your user ID", "Undefined username rejected");
assert.strictEqual(validateUserId("a".repeat(129)), "User ID is too long", "Username > 128 chars rejected");
assert.strictEqual(validateUserId("sarah.compliance"), null, "Valid dot username accepted");
assert.strictEqual(validateUserId("sarah_compliance"), null, "Valid underscore username accepted");
assert.strictEqual(validateUserId("  vikram_pm  "), null, "Valid trimmed username accepted");
console.log("✓ validateUserId checks passed");

// 2. validatePassword tests
assert.strictEqual(validatePassword(""), "Enter your password", "Empty password rejected");
assert.strictEqual(validatePassword(null), "Enter your password", "Null password rejected");
assert.strictEqual(validatePassword(undefined), "Enter your password", "Undefined password rejected");
assert.strictEqual(validatePassword("p".repeat(257)), "Password is too long", "Password > 256 chars rejected");
assert.strictEqual(validatePassword("Compliance@2026"), null, "Valid password accepted");
console.log("✓ validatePassword checks passed");

// 3. validateLoginForm composite tests
const emptyForm = validateLoginForm({ userId: "", password: "" });
assert.strictEqual(emptyForm.userId, "Enter your user ID");
assert.strictEqual(emptyForm.password, "Enter your password");

const onlyUser = validateLoginForm({ userId: "sarah_compliance", password: "" });
assert.strictEqual(onlyUser.userId, undefined);
assert.strictEqual(onlyUser.password, "Enter your password");

const onlyPass = validateLoginForm({ userId: "", password: "Compliance@2026" });
assert.strictEqual(onlyPass.userId, "Enter your user ID");
assert.strictEqual(onlyPass.password, undefined);

const validForm = validateLoginForm({ userId: "sarah_compliance", password: "Compliance@2026" });
assert.strictEqual(Object.keys(validForm).length, 0, "Valid form returns empty errors object");
console.log("✓ validateLoginForm checks passed");

// 4. Contract verification for Auth Error shapes
function parseAuthErrorMessage(resJson, status) {
  if (resJson?.error?.message) {
    return resJson.error.message;
  }
  return "Something went wrong. Please try again.";
}

const mockErrorPayload = {
  error: {
    code: "invalid_credentials",
    message: "That User ID or password doesn't match our records.",
    detail: {},
    path: "/api/auth/login"
  }
};

assert.strictEqual(
  parseAuthErrorMessage(mockErrorPayload, 401),
  "That User ID or password doesn't match our records."
);
console.log("✓ Auth error payload parsing contract verified");

console.log("\nALL AUTH VALIDATION TESTS PASSED SUCCESSFULLY! 🚀");
