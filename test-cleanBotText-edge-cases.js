#!/usr/bin/env node
// Test cleanBotText edge cases

function cleanBotText(text) {
  if (!text) return "";
  let cleaned = String(text);
  
  cleaned = cleaned.replace(/!!!?\s*CONTRIBUTOR\s+TIER[\s\S]*?(?:standard\s+v\d+[\s\S]*?(?=\n\n|Now:|Last:|Next:)|$)/gi, "");
  cleaned = cleaned.replace(/This\s+is\s+Meta'?s?\s+contributor\s+tier[\s\S]*?(?:standard\s+v\d+[\s\S]*?(?=\n\n|Now:|Last:|Next:)|$)/gi, "");
  cleaned = cleaned.replace(/CONTRIBUTOR\s+TIER\s*—\s*TRAINS?\s+ON\s+YOUR\s+DATA/gi, "");
  cleaned = cleaned.replace(/prompts\s+and\s+completions\s+to\s+train\s+future\s+Meta\s+models\.?/gi, "");
  cleaned = cleaned.replace(/See\s+current\s+pricing\s+and\s+rate\s+limits\s+for\s+the\s+Meta\s+Model\s+API[\s\S]*?https?:\/\/[^\s]+/gi, "");
  cleaned = cleaned.replace(/https?:\/\/dev\.meta\.ai\/docs\/pricing-rate-limits?\/?/gi, "");
  cleaned = cleaned.replace(/Do\s+NOT\s+use\s+it\s+for\s+confidential,\s+proprietary,\s+personal,\s+or\s+otherwise\s+sensitive\s+data\.?/gi, "");
  cleaned = cleaned.replace(/For\s+the\s+same\s+model\s+with\s+no\s+training\s+on\s+your\s+data[\s\S]*?(?=\n\n|Now:|Last:|Next:|$)/gi, "");
  cleaned = cleaned.replace(/It\s+lowers\s+the\s+barrier\s+to\s+entry[\s\S]*?acceptable\./gi, "");
  cleaned = cleaned.replace(/security\.allow_data_training_tiers_noninteractive/gi, "");
  cleaned = cleaned.replace(/[┌┐└┘│─]+\s*Scheduled\s+Jobs\s*[┌┐└┘│─]+/gi, "");
  cleaned = cleaned.replace(/Meta\s+Model\s+API\s+is\s+free[\s\S]*?https?:\/\/dev\.meta\.ai\/docs\/pricing-rate-limits?\/?/gi, "");
  
  const lines = cleaned.split('\n').map(line => line.trim()).filter(line => line.length > 0);
  if (lines.length === 1 && /^SMOKE\d+_[A-Z_]+$/i.test(lines[0])) {
    return "";
  }
  
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
  return cleaned.trim();
}

// Test 1: INDEX Last: with mid-line CONTRIBUTOR
const test1 = `Last: Discovered CONTRIBUTOR TIER — TRAINS ON YOUR DATA issue in brief panel. Fixed cleanBotText.`;
const cleaned1 = cleanBotText(test1);
console.log("Test 1: INDEX Last with mid-line CONTRIBUTOR");
console.log("Input:", test1);
console.log("Output:", cleaned1);
console.log("Pass:", !cleaned1.includes("CONTRIBUTOR") && cleaned1.includes("Discovered"));
console.log();

// Test 2: Real content after Meta block
const test2 = `!!! CONTRIBUTOR TIER — TRAINS ON YOUR DATA !!!

This is Meta's contributor tier. Selecting it permits Meta to use your
prompts and completions to train future Meta models.

See current pricing and rate limits for the Meta Model API here:
  https://dev.meta.ai/docs/pricing-rate-limits/

It lowers the barrier to entry for testing. Do NOT use it
for confidential data. For the
same model with no training on your data, select the standard v1

Now: PR #45 merge-ready
Last: Fixed brief panel Meta junk
Next: Test on phone
Blocker: —`;

const cleaned2 = cleanBotText(test2);
console.log("Test 2: Real content after Meta block");
console.log("Output:", cleaned2);
const hasIndex = cleaned2.includes("Now:") && cleaned2.includes("PR #45");
// "Meta" can appear in real content ("brief panel Meta junk"), so check for specific bad phrases
const noContributor = !cleaned2.includes("contributor") && !cleaned2.includes("CONTRIBUTOR");
const noTraining = !cleaned2.includes("train future Meta models");
const noConfidential = !cleaned2.includes("confidential, proprietary, personal");
const noPricing = !cleaned2.includes("pricing-rate-limits");
const noOrphans = !cleaned2.includes("It lowers") && !cleaned2.includes("Do NOT use");
console.log("hasIndex:", hasIndex);
console.log("noContributor:", noContributor);
console.log("noTraining:", noTraining);
console.log("noConfidential:", noConfidential);
console.log("noPricing:", noPricing);
console.log("noOrphans:", noOrphans);
const pass2 = hasIndex && noContributor && noTraining && noConfidential && noPricing && noOrphans;
console.log("Pass:", pass2);
console.log();

// Test 3: Orphan "prompts and completions" fragment
const test3 = `prompts and completions to train future Meta models.

Real content here about SAA Homes project.`;
const cleaned3 = cleanBotText(test3);
console.log("Test 3: Orphan prompts fragment");
console.log("Output:", cleaned3);
console.log("Pass:", !cleaned3.includes("prompts") && cleaned3.includes("SAA Homes"));

const allPass = 
  !cleaned1.includes("CONTRIBUTOR") && cleaned1.includes("Discovered") &&
  pass2 &&
  !cleaned3.includes("prompts") && cleaned3.includes("SAA Homes");

if (!allPass) {
  console.error("\n❌ FAIL: Some edge cases failed");
  process.exit(1);
}

console.log("\n✅ PASS: All edge cases handled");
process.exit(0);
