# RemBG Background Removal API – Developer Docs & Integration Guide
> Site: rembg.com | Services: Remove Background API
> SDK: rembg.js (Node.js wrapper for RemBG API)

Quick Navigation Tabs: NODE.JS | CURL | HTTP | PYTHON

## Installation of rembg.js
npm i @remove-background-ai/rembg.js

## API Reference for rembg.js
@remove-background-ai/rembg.js is a zero-config Node.js wrapper for the free RemBG API, enabling background removal with simple, customizable parameters.

### Parameters for RemBG.js
Parameter	Type	Required	Default	Description
apiKey	string	Required	—	Your Rembg API key
inputImage	string | Buffer | { base64: string }	Required	—	Image file, buffer, or base64 payload
onDownloadProgress	(event) => void	Optional	—	Hook for download progress events
onUploadProgress	(event) => void	Optional	—	Hook for upload progress events
options.format	webp(default) | png	Optional	webp	Specifies the output image format. Either webp (default) or png
options.returnBase64	boolean	Optional	false	Return Base64 string instead of file
options.returnMask	boolean	Optional	false	Return only the alpha mask
options.w	number	Optional	—	Target width (maintains aspect ratio)
options.h	number	Optional	—	Target height (maintains aspect ratio)
options.exact_resize	boolean	Optional	false	Force exact width × height (may distort)
options.angle	number	Optional	0	Rotation angle in degrees
options.expand	boolean	Optional	true	Add padding so rotated images aren’t cropped
options.bg_color	string	Optional	—	Optional solid background color in hex (e.g. #FFFFFF) or named color (e.g. "red", "blue")

### Basic Usage Example
// script.mjs
import { rembg } from '@remove-background-ai/rembg.js';
import dotenv from 'dotenv';

// Load environment variables from .env file
dotenv.config();

// API KEY will be loaded from the .env file
const API_KEY = process.env.API_KEY;

// Log upload and download progress
const onUploadProgress = console.log;
const onDownloadProgress = console.log;

rembg({
    apiKey: API_KEY,
    inputImage: './input.png', // inputImage can be one of these: string | Buffer | { base64: string }
    onUploadProgress,
    onDownloadProgress,
}).then(({ outputPath, cleanup }) => {
    console.log(`✅ Background removed and saved under path: ${outputPath}`);
    // If called, it will cleanup / remove from disk your removed background image
    // cleanup();
});

Remember: the cleanup function can be called if you wish to remove the processed image from your disk after background removal.

### Showing Progress bar
When integrating a background removal service, it’s often beneficial to provide users with feedback on the progress of their upload or download request. To facilitate this, you can define your own onDownloadProgress and onUploadProgress callbacks.
Both of these callbacks accept AxiosProgressEvent as an event parameter. As the request proceeds, these callbacks are invoked multiple times, allowing you to, for instance, display a progress bar and adjust its length based on the progress.

Sample progress output:
{
  loaded: 65587,
  total: 68474,
  progress: 0.95929419831868, // ~95% progress
  bytes: 65587,
  rate: undefined,
  estimated: undefined,
  upload: true // <---- upload progress
}
{
  loaded: 68474,
  total: 68474,
  progress: 1, // <---- 100% progress
  bytes: 2787,
  rate: undefined,
  estimated: undefined,
  upload: true // <---- upload progress
}
{
  loaded: 1002,
  total: 68824,
  progress: 0.0145588741112402, // ~1% progress
  bytes: 1002,
  rate: undefined,
  estimated: undefined,
  download: true // <---- download progress
}
{
  loaded: 68824,
  total: 68824,
  progress: 1, // <---- 100% progress
  bytes: 67822,
  rate: undefined,
  estimated: undefined,
  download: true // <---- download progress
}
✅ Background removed and saved under path/tmp/rembg-xxxx.png

## Membership & Credits Usage
Returns your plan label, included and prepaid credit balances, and usage.
You can query by UTC calendar month (legacy), by Stripe-aligned billing period (for monitoring through renewal), or list known billing periods.
Authenticate with your API key only.
Full schemas, examples, and try-it console: OpenAPI docs

### Endpoint
GET https://www.rembg.com/api/membership-usage

### Authentication
Send your API key via header:
x-api-key: YOUR_API_KEY_HERE
(Create and manage keys in your profile on rembg.com)

### Query parameters
Parameter	Type	Description
year	number	Calendar year (1–9999). With month, reads Redis keys: (uid):app_usage:{year}:{month}. If omitted (and periodStartUnix is not used), defaults to current UTC year.
month	number (1–12)	Calendar month 1–12 (UTC convention used for keys). If omitted, defaults to current UTC month.
periodStartUnix	number	Unix timestamp in seconds; start of a billing window. Reads users: (uid):app_usage:cycle:{periodStartUnix} and api_usage:cycle:... Cannot be combined with year or month.
expand	string	Comma-separated flags. Include billing_cycle to add a billingCycle object current Stripe period when billing_period exists in Redis, otherwise the UTC calendar month. Also works with periodStartUnix for a specific window.
includeBillingCycle	1 / true	Same as expand containing billing_cycle; set to 1 or true to include the billingCycle object.
listBillingCycles	1 / true	Dedicated mode: If listBillingCycles=1 or true returns only { billingCycles: [...] }. Scans Redis for cycle keys for this user; other query parameters are ignored on this request.

⚠️ Do not pass periodStartUnix together with year or month — the API returns 400.
The listBillingCycles mode is separate and ignores other params.

### Example cURL
curl --location 'https://www.rembg.com/api/membership-usage?listBillingCycles=1' \
--header 'x-api-key: YOUR_API_KEY_HERE'

### Example response snippet
{
  "billingCycles": [
    {
      "periodStartUnix": 1779470812,
      "appUsage": 120,
      "credits": 880
    }
  ]
}

### BillingCycle Object Fields
Field	Description
periodStartUnix	Start of the billing window (unix seconds). Matches Stripe current period start when the account is synced.
periodEndUnix	End of the current period window (unix seconds).
appUsage	Usage count inside this window (web editor / API key usage).
includedCredits	Your included (plan) credit allowance as stored in Redis (as top-level credits).
remainingCredits	Total included balance minus used for this billing period. Prepaid consumption is not added here.
stripeBillingSynced	true / false. If false the API falls back to UTC calendar month for usage limits.

Usage logic:
Credits used = includedCredits - remainingCredits for this snapshot.
Prepaid credits exist separately; add prepaidCredits if you want total disposable balance.

### More cURL examples
# Query specific calendar year + month
curl --location 'https://www.rembg.com/api/membership-usage?year=2026&month=3' \
--header 'x-api-key: YOUR_API_KEY_HERE'

# Current subscription full billing block (renew-aligned when Stripe synced)
curl --location 'https://www.rembg.com/api/membership-usage?expand=billing_cycle' \
--header 'x-api-key: YOUR_API_KEY_HERE'

# Historical billing window by stripe period start
curl --location 'https://www.rembg.com/api/membership-usage?periodStartUnix=1779470812&expand=billing_cycle' \
--header 'x-api-key: YOUR_API_KEY_HERE'

### Full Example JSON with billing cycle
{
  "membership": "premium-2000",
  "appUsage": 1800,
  "prepaidCredits": 2000,
  "includedCredits": 1500,
  "remainingCredits": 1700,
  "billingCycle": {
    "periodStartUnix": 1740354960,
    "periodEndUnix": 1742946960,
    "appUsage": 4200,
    "includedCredits": 18500,
    "remainingCredits": 9200,
    "stripeBillingSynced": true
  }
}

## Error Responses
All error responses return a JSON body with a status field matching the HTTP status code.

### Single Error Response Example
HTTP/1.1 400 Bad Request
Content-Type: application/json
{
  "error": "Image width (12000px) exceeds the maximum allowed width of 10000px.",
  "status": 400
}

### Multiple Validation Errors Response
{
  "errors": [
    {"field": "...", "message": "..."},
    {"field": "...", "message": "..."}
  ],
  "status": 400
}

### Error Reference Table
Scenario	Status	Error Message Summary
No image provided	400	No image file provided. Please include an 'image' field in your form data.
No file selected	400	No file selected. Please choose an image file to upload.
Unsupported file type	400	File type .exe is not supported. Allowed formats: webp, png, jpg, jpeg
Empty file (0 bytes)	400	File does not appear to be a valid image (invalid file signature)
File too large	400	File size (55.2 MB) exceeds the maximum allowed size of 50 MB.
Image too wide	400	Image width (12000px) exceeds the maximum allowed width of 10000px.
Image too tall	400	Image height (15000px) exceeds the maximum allowed height of 10000px.
Bad w / h range	400	w must be at least 1, got: -5
Bad w / h max	400	w must be at most 10000, got: 15000
Bad angle max	400	angle must be between -360 and 360 degrees, got: 500.0
Bad output format	400	Invalid format 'gif'. Allowed formats: PNG, WEBP
Bad bg_color	400	RemBG uses #12345 with hex format: #RRGGBB or named color
Mask + bg_color conflict	400	Cannot use mask=true together with bg_color. Choose one or the other.
Invalid API key	401	Invalid api key
Both API key and user token	400	This is a mistake: cannot use both api key and user token
Rate limit exceeded (short-term)	429	You’re making requests too quickly. Please upgrade or slow down.
Rate limit exceeded (daily)	429	You’ve reached your daily limit. Please sign up for more access.
Rate limit exceeded (monthly)	429	You’ve reached your monthly limit. Consider purchasing more credits.

### Error Handling Guidelines
- Check HTTP status code 400 to identify validation errors
- Check the errors array when handling multiple validation parameters
- Use the field detail to map errors to your UI

## Footer Info
Free Tools: Cross-platform Desktop App, CLI Tool, Figma Plugin
Made with ❤️ in Germany
Copyright © 2026 rembg.com, an Arken AI LLC Brand
Links: Status | Blog | Terms of Service | Privacy Policy | Contact | FAQ
