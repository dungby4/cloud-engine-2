const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, '..', 'data');
const ACCOUNTS_CSV_PATH = path.join(DATA_DIR, 'accounts.csv');
const RESULTS_CSV_PATH = path.join(DATA_DIR, 'results.csv');

/**
 * Three strictly separated phone data categories:
 * - mock: Randomly generated VN mobile number strictly for offline/mock testing.
 * - operator: Real phone number controlled by the operator.
 * - verified_input: Real phone number provided by the operator AND confirmed authorized for use.
 */
const PHONE_SOURCE = {
  MOCK: 'mock',
  OPERATOR: 'operator',
  VERIFIED_INPUT: 'verified_input',
  MISSING: 'missing'
};

const VALID_PHONE_SOURCES = new Set([
  PHONE_SOURCE.MOCK,
  PHONE_SOURCE.OPERATOR,
  PHONE_SOURCE.VERIFIED_INPUT,
  PHONE_SOURCE.MISSING
]);

// Valid Vietnamese mobile carrier prefixes (Viettel, Vinaphone, Mobifone, Vietnamobile, Gmobile)
const VN_MOBILE_PREFIXES = [
  '032', '033', '034', '035', '036', '037', '038', '039',
  '096', '097', '098', '086',
  '081', '082', '083', '084', '085', '088', '091', '094',
  '070', '076', '077', '078', '079', '089', '090', '093',
  '056', '058', '092', '059', '099'
];

const VN_MOBILE_REGEX = /^(03|05|07|08|09)[0-9]{8}$/;

/**
 * Generate a random Vietnamese mobile phone number (10 digits).
 * Strictly tagged as `mock` for offline/mock API testing only.
 */
function generateMockVietnamesePhone() {
  const prefix =
    VN_MOBILE_PREFIXES[Math.floor(Math.random() * VN_MOBILE_PREFIXES.length)];
  let suffix = '';
  for (let i = 0; i < 7; i++) {
    suffix += Math.floor(Math.random() * 10).toString();
  }
  return `${prefix}${suffix}`;
}

/**
 * Escape a field for CSV output
 */
function escapeCsvField(val) {
  if (val === null || val === undefined) return '';
  const str = String(val);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

/**
 * Parse a single CSV line handling quoted values
 */
function parseCsvLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else {
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ',') {
        result.push(current.trim());
        current = '';
      } else {
        current += ch;
      }
    }
  }
  result.push(current.trim());
  return result;
}

/**
 * Generate the default list of 70 accounts (dungby30 -> dungby99).
 * - dungby30: Already confirmed REGISTERED on Funtap (FunID 386579063) using operator's verified input.
 * - dungby31..dungby99: Assigned unique `mock` phone numbers for offline testing.
 */
function generateDefaultAccountsList() {
  const accounts = [];
  const usedPhones = new Set();
  let order = 1;

  for (let num = 30; num <= 99; num++) {
    const username = `dungby${num}`;
    let phone = generateMockVietnamesePhone();
    while (usedPhones.has(phone)) {
      phone = generateMockVietnamesePhone();
    }
    usedPhones.add(phone);

    const isConfirmedDungby30 = num === 30;
    const envPhone = process.env.FUNTAP_TEST_PHONE || '';
    if (isConfirmedDungby30 && VN_MOBILE_REGEX.test(envPhone) && !usedPhones.has(envPhone)) {
      phone = envPhone;
      usedPhones.add(phone);
    }

    accounts.push({
      index: order,
      username,
      fullname: `Dung ${num}`,
      phone,
      phone_source: isConfirmedDungby30 ? PHONE_SOURCE.VERIFIED_INPUT : PHONE_SOURCE.MOCK,
      birthday: '1995-05-15'
    });
    order++;
  }
  return accounts;
}

/**
 * Write data/accounts.csv preserving phone_source and optional status/funid/login_verified columns
 */
function writeAccountsCsv(accounts, targetPath = ACCOUNTS_CSV_PATH) {
  const dir = path.dirname(targetPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  const hasExtendedCols = accounts.some(
    (a) => a.status !== undefined || a.funid !== undefined || a.login_verified !== undefined
  );
  const header = hasExtendedCols
    ? 'index,username,fullname,phone,phone_source,birthday,status,funid,login_verified'
    : 'index,username,fullname,phone,phone_source,birthday';

  const rows = accounts.map((acc, idx) => {
    const phoneStr = (acc.phone || '').trim();
    const defaultSrc = phoneStr ? PHONE_SOURCE.MOCK : PHONE_SOURCE.MISSING;
    const baseCols = [
      acc.index || idx + 1,
      escapeCsvField(acc.username),
      escapeCsvField(acc.fullname),
      escapeCsvField(phoneStr),
      escapeCsvField(
        VALID_PHONE_SOURCES.has(acc.phone_source) ? acc.phone_source : defaultSrc
      ),
      escapeCsvField(acc.birthday || '1995-05-15')
    ];
    if (hasExtendedCols) {
      baseCols.push(
        escapeCsvField(acc.status || ''),
        escapeCsvField(acc.funid || ''),
        escapeCsvField(acc.login_verified !== undefined ? acc.login_verified : '')
      );
    }
    return baseCols.join(',');
  });
  fs.writeFileSync(targetPath, [header, ...rows].join('\n') + '\n', 'utf8');
}

/**
 * Ensure data/accounts.csv exists without generating unowned phone numbers for rows missing a phone.
 */
function ensureAccountsCsvExists(forceRegenerate = false) {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
  if (!fs.existsSync(ACCOUNTS_CSV_PATH) || forceRegenerate) {
    const defaultAccounts = generateDefaultAccountsList();
    writeAccountsCsv(defaultAccounts);
    return;
  }

  const content = fs.readFileSync(ACCOUNTS_CSV_PATH, 'utf8').trim();
  const lines = content.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length <= 1) {
    writeAccountsCsv(generateDefaultAccountsList());
    return;
  }
}

/**
 * Load accounts from data/accounts.csv
 */
function loadAccounts(customPath = ACCOUNTS_CSV_PATH) {
  if (customPath === ACCOUNTS_CSV_PATH) {
    ensureAccountsCsvExists(false);
  }
  if (!fs.existsSync(customPath)) return [];

  const content = fs.readFileSync(customPath, 'utf8').trim();
  if (!content) return [];
  const lines = content.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length <= 1) return [];

  const headers = parseCsvLine(lines[0]);
  const accounts = [];

  for (let i = 1; i < lines.length; i++) {
    const cols = parseCsvLine(lines[i]);
    const row = {};
    headers.forEach((h, idx) => {
      row[h] = cols[idx] !== undefined ? cols[idx] : '';
    });
    const phone = (row.phone || '').trim();
    const rawSource = (row.phone_source || '').trim().toLowerCase();
    const phoneSource = VALID_PHONE_SOURCES.has(rawSource)
      ? rawSource
      : phone
      ? PHONE_SOURCE.MOCK
      : PHONE_SOURCE.MISSING;

    const item = {
      index: Number(row.index) || i,
      username: (row.username || `dungby${29 + i}`).trim(),
      fullname: (row.fullname || `Dung ${29 + i}`).trim(),
      phone,
      phone_source: phoneSource,
      birthday: (row.birthday || '1995-05-15').trim()
    };
    if (row.status !== undefined) item.status = row.status;
    if (row.funid !== undefined) item.funid = row.funid;
    if (row.login_verified !== undefined) item.login_verified = row.login_verified;
    accounts.push(item);
  }
  return accounts;
}

/**
 * Safely import/merge real operator phone numbers from an external CSV file into accounts list.
 *
 * Security & Integrity Rules:
 * 1. NEVER allow relabeling an existing `mock` phone number as `operator` or `verified_input`
 *    if the phone number itself is identical to the previously generated mock number!
 * 2. Reject invalid VN mobile numbers or duplicate phone numbers across the dataset.
 * 3. Only set `verified_input` if `operatorConfirmed === true` (or row explicitly has `verified_input` with a new real phone); otherwise set `operator`.
 */
function mergeOperatorPhonesFromCsv(accounts, externalCsvPath, options = {}) {
  if (!fs.existsSync(externalCsvPath)) {
    throw new Error(`External phone CSV file not found: ${externalCsvPath}`);
  }

  const content = fs.readFileSync(externalCsvPath, 'utf8').trim();
  const lines = content.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length <= 1) {
    return { updatedCount: 0, rejected: ['External CSV is empty'], accounts };
  }

  const headers = parseCsvLine(lines[0]);
  const externalMap = new Map();
  for (let i = 1; i < lines.length; i++) {
    const cols = parseCsvLine(lines[i]);
    const row = {};
    headers.forEach((h, idx) => {
      row[h] = cols[idx] !== undefined ? cols[idx] : '';
    });
    const username = (row.username || '').trim();
    const phone = (row.phone || '').trim();
    const requestedSource = (row.phone_source || '').trim().toLowerCase();
    if (username && phone) {
      externalMap.set(username, { phone, requestedSource, rowNumber: i + 1 });
    }
  }

  // Track all existing mock phones so we never allow relabeling a mock phone as real
  const existingMockPhones = new Set(
    accounts.filter((a) => a.phone_source === PHONE_SOURCE.MOCK).map((a) => a.phone)
  );
  const usedRealPhones = new Set(
    accounts.filter((a) => a.phone_source !== PHONE_SOURCE.MOCK).map((a) => a.phone)
  );

  let updatedCount = 0;
  const rejected = [];

  const updatedAccounts = accounts.map((acc) => {
    const ext = externalMap.get(acc.username);
    if (!ext) return acc;

    if (!VN_MOBILE_REGEX.test(ext.phone)) {
      rejected.push(
        `${acc.username}: Rejected invalid VN mobile phone format in external CSV (row ${ext.rowNumber})`
      );
      return acc;
    }

    // Rule: Cannot relabel an existing mock phone into operator/verified_input!
    if (existingMockPhones.has(ext.phone)) {
      rejected.push(
        `${acc.username}: Prohibited attempt to relabel existing mock phone as ${
          ext.requestedSource || 'operator'
        } without providing a distinct real phone number`
      );
      return acc;
    }

    if (usedRealPhones.has(ext.phone) && acc.phone !== ext.phone) {
      rejected.push(
        `${acc.username}: Duplicate real phone number already assigned to another account`
      );
      return acc;
    }

    usedRealPhones.add(ext.phone);
    updatedCount++;

    const targetSource =
      options.verifiedInput === true || ext.requestedSource === PHONE_SOURCE.VERIFIED_INPUT
        ? PHONE_SOURCE.VERIFIED_INPUT
        : PHONE_SOURCE.OPERATOR;

    return {
      ...acc,
      phone: ext.phone,
      phone_source: targetSource
    };
  });

  return {
    updatedCount,
    rejected,
    accounts: updatedAccounts
  };
}

function ensureResultsCsvExists() {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
  if (!fs.existsSync(RESULTS_CSV_PATH)) {
    const header =
      'username,funid,status,mock_status,processed_at,error_message,index,fullname,phone,phone_source,mode,login_verified,notes\n';
    fs.writeFileSync(RESULTS_CSV_PATH, header, 'utf8');
  }
}

function loadCompletedUsernames() {
  ensureResultsCsvExists();
  const content = fs.readFileSync(RESULTS_CSV_PATH, 'utf8').trim();
  const completed = new Map();
  if (!content) return completed;

  const lines = content.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length <= 1) return completed;

  const headers = parseCsvLine(lines[0]);
  for (let i = 1; i < lines.length; i++) {
    const cols = parseCsvLine(lines[i]);
    const row = {};
    headers.forEach((h, idx) => {
      row[h] = cols[idx] !== undefined ? cols[idx] : '';
    });
    if (row.username) {
      completed.set(row.username, row);
    }
  }
  return completed;
}

function appendResult(record) {
  ensureResultsCsvExists();
  const line = [
    escapeCsvField(record.username),
    escapeCsvField(record.funid || ''),
    escapeCsvField(record.status),
    escapeCsvField(record.mock_status || ''),
    escapeCsvField(record.timestamp || new Date().toISOString()),
    escapeCsvField(record.validationSummary || ''),
    escapeCsvField(record.index),
    escapeCsvField(record.fullname),
    escapeCsvField(record.phone ? maskPhone(record.phone) : ''),
    escapeCsvField(record.phoneSource || PHONE_SOURCE.MOCK),
    escapeCsvField(record.mode || 'dry-run'),
    escapeCsvField(Boolean(record.login_verified)),
    escapeCsvField(record.notes || '')
  ].join(',');
  fs.appendFileSync(RESULTS_CSV_PATH, line + '\n', 'utf8');
}

function maskPhone(phone) {
  const clean = String(phone).trim();
  if (clean.length <= 4) return clean;
  return clean.slice(0, 3) + '***' + clean.slice(-3);
}

module.exports = {
  ACCOUNTS_CSV_PATH,
  RESULTS_CSV_PATH,
  PHONE_SOURCE,
  VALID_PHONE_SOURCES,
  VN_MOBILE_REGEX,
  escapeCsvField,
  parseCsvLine,
  generateMockVietnamesePhone,
  generateDefaultAccountsList,
  writeAccountsCsv,
  ensureAccountsCsvExists,
  mergeOperatorPhonesFromCsv,
  ensureResultsCsvExists,
  loadAccounts,
  loadCompletedUsernames,
  appendResult,
  maskPhone
};
