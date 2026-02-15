# QSOL Syntax Highlighting (VS Code)

This folder contains a TextMate-based VS Code language extension for `.qsol` files.

## Included

- TextMate grammar: `syntaxes/qsol.tmLanguage.json`
- Language config (comments, brackets, folding): `language-configuration.json`
- Extension manifest: `package.json`
- Keyword and declaration highlighting for dotted module imports (`use stdlib.module;`, `use user.module;`)
- Quoted-path imports are not part of the language (`use "x.qsol";` is invalid)

## Run in development

1. Open `qsol/editors/vscode-qsol` in VS Code.
2. Press `F5` to launch an Extension Development Host.
3. Open a `.qsol` file and verify highlighting.

## Package and install

1. Install the packager:

   ```bash
   npm install -g @vscode/vsce
   ```

2. Build a `.vsix`:

   ```bash
   vsce package
   ```

3. Install the generated file:

   ```bash
   code --install-extension qsol-syntax-0.1.0.vsix
   ```
