import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const screenshotsDir = path.join(__dirname, "test_screenshots");
if (!fs.existsSync(screenshotsDir)) {
  fs.mkdirSync(screenshotsDir, { recursive: true });
}

const FRONTEND_URL = "http://localhost:5173";

const QUERIES = [
  // --- Initial 4 Core Queries ---
  {
    id: "Q01_TOP10_SCHEMES_AUM",
    title: "Top 10 Mutual Fund Schemes by Average AUM",
    query: "What are the top 10 mutual fund schemes with the highest Average AUM (in ₹ Crores), and which AMCs manage them?",
    expectedKeyFacts: [
      "SBI Nifty 50 ETF",
      "SBI Funds Management Limited",
      "210,783",
    ],
  },
  {
    id: "Q02_TOP_AMCS_AUM",
    title: "AMCs Managing Highest Total AUM & Scheme Counts",
    query: "Which Asset Management Companies (AMCs) manage the highest total AUM, and how many distinct schemes does each AMC offer?",
    expectedKeyFacts: [
      "SBI Funds Management Limited",
      "1,260,906",
      "ICICI Prudential",
      "Distinct Schemes",
    ],
  },
  {
    id: "Q03_CATEGORY_BREAKDOWN",
    title: "Category Breakdown of Total AUM and Scheme Counts",
    query: "What is the breakdown of total AUM and number of schemes across different mutual fund categories?",
    expectedKeyFacts: [
      "Equity Schemes",
      "Debt Schemes",
      "3,517,433",
      "42.45%",
    ],
  },
  {
    id: "Q04_EQUITY_GROWTH_NAV",
    title: "Highest NAV Open-ended Equity Growth Schemes",
    query: "Which open-ended Equity Growth schemes currently have the highest NAV?",
    expectedKeyFacts: [
      "Nippon India Growth Mid Cap",
      "4,908.69",
      "Franklin India Mid Cap",
      "HDFC Flexi Cap",
    ],
  },

  // --- 16 Additional Unique & Distinct Queries ---
  {
    id: "Q05_HDFC_AMC_TOTAL",
    title: "HDFC AMC Total AUM and Scheme Count",
    query: "What is the total Average AUM managed by HDFC Asset Management Company Limited, and how many schemes do they offer?",
    expectedKeyFacts: [
      "HDFC Asset Management Company Limited",
      "952,359.70",
      "108",
    ],
  },
  {
    id: "Q06_TATA_AMC_TOTAL",
    title: "Tata Asset Management Limited Total AUM",
    query: "What is the total AUM managed by Tata Asset Management Limited?",
    expectedKeyFacts: [
      "Tata Asset Management Limited",
      "229,419.21",
      "65",
    ],
  },
  {
    id: "Q07_PPFAS_AMC_TOTAL",
    title: "PPFAS AMC Total AUM Across Schemes",
    query: "How much total AUM does PPFAS Asset Management Pvt. Ltd. manage across its schemes?",
    expectedKeyFacts: [
      "PPFAS Asset Management Pvt. Ltd.",
      "152,328.16",
    ],
  },
  {
    id: "Q08_QUANT_AMC_TOTAL",
    title: "Quant AMC Total AUM in Dataset",
    query: "What is the total AUM managed by Quant Money Managers Limited in the dataset?",
    expectedKeyFacts: [
      "quant Money Managers Limited",
      "88,362.53",
      "29",
    ],
  },
  {
    id: "Q09_PARAG_PARIKH_FLEXI_CAP",
    title: "Parag Parikh Flexi Cap Fund Total AUM Across Plan Variants",
    query: "What is the total Average AUM of Parag Parikh Flexi Cap Fund across its plan variants?",
    expectedKeyFacts: [
      "Parag Parikh Flexi Cap Fund",
      "PPFAS Asset Management Pvt. Ltd.",
      "133,447.85",
      "4",
    ],
  },
  {
    id: "Q10_SBI_NIFTY_50_ETF",
    title: "SBI Nifty 50 ETF Average AUM and Managing AMC",
    query: "What is the Average AUM of SBI Nifty 50 ETF and which AMC manages it?",
    expectedKeyFacts: [
      "SBI Nifty 50 ETF",
      "SBI Funds Management Limited",
      "210,783.07",
    ],
  },
  {
    id: "Q11_LIQUID_FUNDS_TOP5",
    title: "Top 5 Schemes in Liquid Fund Category",
    query: "What are the top 5 schemes in the Liquid Fund category with the highest AUM?",
    expectedKeyFacts: [
      "SBI LIQUID FUND",
      "56,876.63",
      "HDFC Liquid Fund",
      "48,461.88",
    ],
  },
  {
    id: "Q12_LARGE_CAP_TOP_AUM",
    title: "Large Cap Schemes with Highest Average AUM",
    query: "Which Large Cap mutual fund schemes have the highest Average AUM?",
    expectedKeyFacts: [
      "ICICI Prudential Large Cap Fund",
      "SBI Large Cap Fund",
      "Nippon India Large Cap Fund",
    ],
  },
  {
    id: "Q13_SMALL_CAP_TOP_AUM",
    title: "Top Small Cap Mutual Fund Schemes Ranked by AUM",
    query: "What are the top Small Cap mutual fund schemes ranked by AUM?",
    expectedKeyFacts: [
      "Nippon India Small Cap Fund",
      "45,272.23",
      "HDFC Small Cap Fund",
      "SBI SMALL CAP FUND",
    ],
  },
  {
    id: "Q14_FLEXI_CAP_TOP_AUM",
    title: "Flexi Cap Schemes with Largest AUM",
    query: "Which Flexi Cap mutual fund schemes have the largest AUM?",
    expectedKeyFacts: [
      "Parag Parikh Flexi Cap Fund",
      "HDFC Flexi Cap Fund",
      "Kotak Flexicap Fund",
    ],
  },
  {
    id: "Q15_ELSS_TAX_SAVING_TOP",
    title: "Top ELSS Tax-Saving Schemes by AUM and Managing AMCs",
    query: "What are the top ELSS tax-saving schemes by AUM and which AMCs manage them?",
    expectedKeyFacts: [
      "SBI ELSS Tax Saver Fund",
      "Axis ELSS Tax Saver Fund",
      "Mirae Asset ELSS Tax Saver Fund",
      "HDFC ELSS Tax saver",
    ],
  },
  {
    id: "Q16_CLOSE_ENDED_SUMMARY",
    title: "Close Ended Schemes Count and Total AUM",
    query: "How many Close Ended schemes exist in the dataset and what is their total AUM?",
    expectedKeyFacts: [
      "Close Ended",
      "19,790.16",
      "1,446",
      "6,163",
    ],
  },
  {
    id: "Q17_LOWEST_NAV_SCHEMES",
    title: "Mutual Fund Schemes with Lowest NAV in Dataset",
    query: "Which mutual fund schemes in the dataset have the lowest NAV?",
    expectedKeyFacts: [
      "Lowest NAV",
      "0.0",
    ],
  },
  {
    id: "Q18_DEBT_HIGHEST_NAV",
    title: "Highest NAV Open-Ended Debt Schemes",
    query: "Which open-ended Debt schemes have the highest NAV?",
    expectedKeyFacts: [
      "Debt",
      "Highest NAV",
    ],
  },
  {
    id: "Q19_OVERALL_DATASET_SUMMARY",
    title: "Total Average AUM and Distinct Schemes Across Entire Dataset",
    query: "What is the total Average AUM and total number of distinct schemes across the entire mutual fund dataset?",
    expectedKeyFacts: [
      "8,285,213.96",
      "3,696",
      "54",
      "16,245",
    ],
  },
  {
    id: "Q20_TOP5_AMCS_RANKING",
    title: "Top 5 Asset Management Companies by Total AUM",
    query: "List the top 5 Asset Management Companies by total AUM in India.",
    expectedKeyFacts: [
      "SBI Funds Management Limited",
      "ICICI Prudential",
      "HDFC Asset Management",
      "Nippon Life India",
      "Kotak Mahindra",
    ],
  },
];

async function runBrowserE2E() {
  console.log("==================================================================");
  console.log("Starting End-to-End Browser Test via Playwright & Microsoft Edge");
  console.log("Frontend URL:", FRONTEND_URL);
  console.log(`Executing ${QUERIES.length} Unique Real-World Mutual Fund Queries`);
  console.log("==================================================================");

  const report = {
    startedAt: new Date().toISOString(),
    frontendUrl: FRONTEND_URL,
    totalQueries: QUERIES.length,
    queries: [],
    consoleErrors: [],
    apiCalls: [],
  };

  const browser = await chromium.launch({
    channel: "msedge",
    headless: true,
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });

  const page = await context.newPage();

  // Listen to console and network
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      report.consoleErrors.push({ text: msg.text(), location: msg.location() });
    }
  });

  page.on("response", (resp) => {
    const url = resp.url();
    if (url.includes("/api/")) {
      report.apiCalls.push({
        url,
        status: resp.status(),
        method: resp.request().method(),
      });
    }
  });

  try {
    // 1. Navigation & Authentication
    console.log("\n[Step 1] Navigating to Frontend at:", FRONTEND_URL);
    await page.goto(FRONTEND_URL, { waitUntil: "domcontentloaded", timeout: 30000 });

    const loginInput = await page.waitForSelector("#login-user-id", { timeout: 8000 }).catch(() => null);
    if (loginInput) {
      console.log("  Logging in as amc_admin...");
      await page.fill("#login-user-id", "amc_admin");
      await page.fill("#login-password", "Compliance@2026");
      await page.click("button.login-submit-btn");
      await page.waitForSelector(".cg-chatgpt-query-input", { timeout: 15000 });
      console.log("  ✓ Successfully logged into Dashboard (Chat Input visible)!");
    } else {
      console.log("  Already logged in or login not required.");
    }

    await page.waitForTimeout(1500);

    // 2. Loop through each CSV query
    for (let i = 0; i < QUERIES.length; i++) {
      const qObj = QUERIES[i];
      console.log(`\n------------------------------------------------------------------`);
      console.log(`[Query ${i + 1}/${QUERIES.length}] ${qObj.title}`);
      console.log(`Prompt: "${qObj.query}"`);
      console.log(`------------------------------------------------------------------`);

      const tStart = Date.now();

      // Clear input and focus
      const input = await page.waitForSelector(".cg-chatgpt-query-input", { timeout: 10000 });
      await input.click();
      await page.keyboard.press("Control+A");
      await page.keyboard.press("Backspace");
      await input.fill(qObj.query);
      await page.waitForTimeout(300);

      // Verify input value in DOM
      const val = await input.inputValue();
      if (val !== qObj.query) {
        await input.fill(qObj.query);
      }

      // Count existing finalized answers before submitting
      const prevAnswerCount = await page.$$eval(".cg-answer", els => els.length).catch(() => 0);

      // Click Send
      const sendBtn = await page.waitForSelector("button.cg-chatgpt-send-btn", { timeout: 5000 });
      await sendBtn.click();
      console.log("  Query submitted. Waiting for streaming response to complete...");

      // Wait for a new answer container to appear in the DOM
      await page.waitForFunction(
        (prev) => document.querySelectorAll(".cg-answer").length > prev,
        prevAnswerCount,
        { timeout: 60000 }
      );

      // Wait for streaming indicator to finish
      await page.waitForSelector("button.cg-chatgpt-send-btn:not(.cg-chatgpt-send-btn--streaming)", {
        timeout: 60000,
      });

      // Allow UI render settling
      await page.waitForTimeout(1500);

      const elapsedMs = Date.now() - tStart;
      console.log(`  ✓ Response received in ${(elapsedMs / 1000).toFixed(2)}s`);

      // Extract the newly added assistant answer
      const answers = await page.$$(".cg-answer");
      const latestAnswerEl = answers[answers.length - 1];
      const answerText = await latestAnswerEl.innerText();
      console.log("\n  --- [UI Answer Preview] ---");
      const previewLines = answerText.split("\n").filter(l => l.trim()).slice(0, 8);
      previewLines.forEach(l => console.log("    " + l));
      console.log("  --- [End Preview] ---\n");

      // Check evidence modal
      let evidenceDetails = null;
      try {
        const evidenceBtns = await page.$$("button:has-text('Evidence')");
        if (evidenceBtns.length > 0) {
          const latestEvBtn = evidenceBtns[evidenceBtns.length - 1];
          await latestEvBtn.click();
          await page.waitForSelector(".cg-modal-card", { timeout: 5000 });
          
          const modalText = await page.innerText(".cg-modal-card");
          evidenceDetails = {
            preview: modalText.slice(0, 300).replace(/\s+/g, " "),
          };
          console.log("  ✓ Evidence modal verified:", evidenceDetails.preview.slice(0, 100) + "...");

          // Close modal
          const closeBtn = await page.$(".cg-modal-close-btn");
          if (closeBtn) {
            await closeBtn.click();
          } else {
            await page.keyboard.press("Escape");
          }
          await page.waitForSelector(".cg-modal-overlay", { state: "hidden", timeout: 5000 });
        }
      } catch (evErr) {
        console.warn("  Evidence modal check note:", evErr.message);
      }

      // Take screenshot of answer in UI
      const screenshotPath = path.join(screenshotsDir, `${qObj.id}.png`);
      await page.screenshot({ path: screenshotPath, fullPage: false });
      console.log(`  ✓ Screenshot saved: ${path.basename(screenshotPath)}`);

      // Verify facts against expected ground truth
      const verificationResults = [];
      let allPassed = true;
      for (const fact of qObj.expectedKeyFacts) {
        const found = answerText.toLowerCase().includes(fact.toLowerCase());
        verificationResults.push({
          expectedFact: fact,
          foundInUI: found,
        });
        if (!found) allPassed = false;
      }

      console.log("  Fact Verification Summary:");
      verificationResults.forEach((vr) => {
        console.log(`    ${vr.foundInUI ? "✓ PASS" : "✗ FAIL"}: [${vr.expectedFact}]`);
      });

      report.queries.push({
        id: qObj.id,
        title: qObj.title,
        query: qObj.query,
        elapsedSeconds: (elapsedMs / 1000).toFixed(2),
        answerText,
        answerLength: answerText.length,
        evidenceDetails,
        verificationResults,
        allFactsVerified: allPassed,
        screenshotFile: path.basename(screenshotPath),
      });

      // Brief pause before next query
      await page.waitForTimeout(600);
    }

    report.completedAt = new Date().toISOString();
    report.summary = {
      totalQueries: QUERIES.length,
      passedQueries: report.queries.filter(q => q.allFactsVerified).length,
      failedQueries: report.queries.filter(q => !q.allFactsVerified).length,
    };

    console.log("\n==================================================================");
    console.log(`E2E Browser Test Finished: ${report.summary.passedQueries}/${report.summary.totalQueries} Queries 100% Verified!`);
    console.log("==================================================================");

    const reportPath = path.join(__dirname, "browser_test_report.json");
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf-8");
    console.log("Detailed report saved to:", reportPath);

  } catch (err) {
    console.error("Browser E2E Fatal Error:", err);
    report.fatalError = err.message;
  } finally {
    await browser.close();
  }
}

runBrowserE2E();
