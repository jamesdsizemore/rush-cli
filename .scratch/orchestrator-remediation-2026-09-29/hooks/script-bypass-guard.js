// PROPOSED (D9), not registered. PreToolUse, matcher Bash. Denies (a) `bash|sh|zsh|python|python3|node <file>` when Write
// or Edit created or changed <file> earlier in this session and it has a line that starts with a raw command the rtk
// hook denies (git, cat, head, tail, ls, wc, grep, find, sed); (b) writing under docs/ with cp, mv, tee or sed -i.
// The denial names the line. Unlock: the human's whole message is exactly `allow`.
const { fs, path, lastHumanText, unlocked, writtenThisSession, readInput, approve, block } = require('./behavior-lib.js');
const RAW = /^\s*(git|cat|head|tail|ls|wc|grep|find|sed)\s/;
readInput((input) => {
  if (input.tool_name !== 'Bash') return approve();
  const cmd = String((input.tool_input && input.tool_input.command) || '');
  if (unlocked(lastHumanText(input.transcript_path || ''), 'allow')) return approve();
  const run = cmd.match(/^\s*(?:bash|sh|zsh|python3?|node)\s+(?:-\w+\s+)*(\S+)/);
  if (run) {
    const file = path.resolve(input.cwd || process.cwd(), run[1].replace(/^~/, process.env.HOME || '~'));
    if (fs.existsSync(file) && writtenThisSession(input.transcript_path || '', file)) {
      const hit = fs.readFileSync(file, 'utf8').split('\n').find((l) => RAW.test(l));
      if (hit) return block(`${run[1]} was written this session and holds a raw command line the rtk hook denies: "${hit.trim().slice(0, 80)}". Type the rtk form as its own command instead. Unlock: the user sends exactly \`allow\`.`);
    }
  }
  if (/\b(cp|mv|tee|sed\s+-i)\b[^|;&\n]*\bdocs\//.test(cmd)) {
    return block('A write under docs/ through cp, mv, tee or sed -i goes around the Edit and Write guards. Use Edit or Write. Unlock: the user sends exactly `allow`.');
  }
  approve();
});
