import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const user = process.env.BONSAI_USER ?? 'george-cliff';
const token = process.env.GITHUB_TOKEN;
const sourceDir = path.resolve(process.env.BONSAI_SOURCE_DIR ?? '.git-bonsai-source');
const sourceRef = process.env.BONSAI_SOURCE_REF ?? 'v1.0.0';
const outputDir = path.resolve('output');

if (!token) throw new Error('GITHUB_TOKEN is required');

const require = createRequire(import.meta.url);
const engine = require(path.join(sourceDir, 'dist', 'src', 'index.js'));
const metrics = await engine.fetchMetrics(user, token);
const bonsai = engine.generate(metrics, { season: 'auto' });
const sourceCommit = execFileSync('git', ['-C', sourceDir, 'rev-parse', 'HEAD'], {
  encoding: 'utf8',
}).trim();

const snapshot = {
  schemaVersion: 1,
  generatedAt: new Date().toISOString(),
  source: {
    repository: 'egorthinks/git-bonsai',
    ref: sourceRef,
    commit: sourceCommit,
  },
  season: engine.seasonFromDate(metrics.fetchedAt),
  metrics,
  dna: bonsai.dna,
};

mkdirSync(outputDir, { recursive: true });
writeFileSync(path.join(outputDir, 'bonsai.svg'), bonsai.svg);
writeFileSync(path.join(outputDir, 'bonsai.png'), bonsai.png);
writeFileSync(path.join(outputDir, 'bonsai.gif'), bonsai.gif);
writeFileSync(path.join(outputDir, 'bonsai-growth.gif'), bonsai.growthGif);
writeFileSync(path.join(outputDir, 'bonsai-data.json'), `${JSON.stringify(snapshot, null, 2)}\n`);

console.log(
  `Generated ${bonsai.dna.style} ${bonsai.dna.species} bonsai profile and website assets from one metrics snapshot.`,
);
