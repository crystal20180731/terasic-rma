import { webcrypto } from 'crypto';
import fs from 'fs';
const { subtle } = webcrypto;
const pw = process.argv[2] || 'sales7508@terasic';
const buf = fs.readFileSync('site/data.enc');
const bytes = new Uint8Array(buf);
const salt = bytes.slice(0, 16);
const nonce = bytes.slice(16, 28);
const ct = bytes.slice(28);
const enc = new TextEncoder();
const keyMat = await subtle.importKey('raw', enc.encode(pw), 'PBKDF2', false, ['deriveKey']);
const key = await subtle.deriveKey({ name: 'PBKDF2', salt, iterations: 200000, hash: 'SHA-256' }, keyMat, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
const plain = await subtle.decrypt({ name: 'AES-GCM', iv: nonce }, key, ct);
const text = new TextDecoder().decode(plain);
const json = JSON.parse(text);
console.log('✓ 解密成功');
console.log('  记录数:', json.count, '| 保固待核:', json.mismatchCount, '| 更新:', json.updated);
console.log('  第一条:', json.records[0].rma, '|', json.records[0].company);
// 错误口令测试
try {
  const bad = await subtle.importKey('raw', enc.encode('wrong'), 'PBKDF2', false, ['deriveKey']);
  const bk = await subtle.deriveKey({ name: 'PBKDF2', salt, iterations: 200000, hash: 'SHA-256' }, bad, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
  await subtle.decrypt({ name: 'AES-GCM', iv: nonce }, bk, ct);
  console.log('✗ 错误口令竟然解密成功（不安全！）');
} catch (e) {
  console.log('✓ 错误口令解密失败（安全）');
}
