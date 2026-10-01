# Code-signing the Windows build

Unsigned downloads trigger Windows SmartScreen's "Windows protected your PC" warning. Signing the
installer and the portable exe with a code-signing certificate removes the "unknown publisher"
label. A new certificate still builds SmartScreen reputation over the first few hundred downloads.

The cheapest route for an open-source project is **SignPath Foundation**, which signs open-source
releases for free with its own certificate. The release workflow is already wired for it: the
signing steps in `.github/workflows/windows.yml` are skipped until the settings below exist.

## 1. Apply

1. Read the conditions at <https://signpath.org> (open-source license, built from public source
   on GitHub Actions, a visible code-signing policy).
2. Add a **Code signing policy** section to the README. SignPath gives you the text: it names
   SignPath Foundation as the certificate holder and you as the approver.
3. Apply through the form on signpath.org with the repository URL
   `https://github.com/ZodchiSama/RINNE`. Approval takes from a few days to a few weeks.

## 2. Set up the SignPath project

Once you're accepted, in the SignPath web app:

1. Create a project with the slug **`rinne`** and link it to the GitHub repository (trusted build
   system: GitHub.com).
2. Add an **artifact configuration** describing the zip that GitHub Actions uploads:

   ```xml
   <?xml version="1.0" encoding="utf-8"?>
   <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
     <zip-file>
       <pe-file path="Rinne-Setup-*.exe" max-matches="1">
         <authenticode-sign/>
       </pe-file>
       <pe-file path="Rinne-Portable-*.exe" max-matches="1">
         <authenticode-sign/>
       </pe-file>
     </zip-file>
   </artifact-configuration>
   ```

3. Create a signing policy with the slug **`release-signing`**, using the certificate SignPath
   assigned to you.
4. Create an API token for a CI user that is allowed to submit to that policy.

## 3. Connect the repository

On GitHub, open **Settings → Secrets and variables → Actions**:

- **Variables** tab: add `SIGNPATH_ORGANIZATION_ID` with your organization ID (it's in the
  SignPath URL and on the organization's settings page).
- **Secrets** tab: add `SIGNPATH_API_TOKEN` with the token from step 2.4.

The next `v*` tag then uploads the two exe files to SignPath, waits for the signing request to be
approved (approve it in the SignPath web app if the policy requires manual approval), and attaches
the signed files to the release in place of the unsigned ones.

## Optional: signing the app inside the installer

The steps above sign the files people download, which is what SmartScreen checks. To also sign
`Rinne.exe` inside the installer, add a second artifact configuration and signing request for
`dist/Rinne/` after "Build app folder", before "Build installer".

## Other options

- **Azure Trusted Signing** costs about US$10 a month. It needs a business or individual identity
  verification and works with the `azure/trusted-signing-action` GitHub action.
- **A certificate from a CA** (Certum's open-source certificate, Sectigo, etc.) is now issued on a
  hardware token or cloud HSM, which makes CI signing awkward. It's better avoided here.
