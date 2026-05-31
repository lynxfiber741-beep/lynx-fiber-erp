# PWA Setup Instructions for Lynx Fiber ERP

## What's Been Added

### 1. PWA Manifest File (`manifest.json`)
- App name: Lynx Fiber ERP
- Theme colors configured
- App shortcuts added
- Icon placeholders configured

### 2. Service Worker (`sw.js`)
- Offline caching enabled
- Cache-first strategy
- Automatic cache cleanup

### 3. Mobile-Responsive CSS
- Tablet support (768px and below)
- Mobile support (480px and below)
- Optimized fonts and spacing
- Touch-friendly tables

### 4. PWA Install Button
- Added to sidebar
- Shows installation instructions
- Guides users to install app

## What You Need to Do

### Step 1: Add App Icons

Create two PNG icon files in the project root:

**icon-192.png** (192x192 pixels)
- Use your company logo
- Transparent background recommended
- Simple design works best

**icon-512.png** (512x512 pixels)
- Same design as icon-192.png
- Higher resolution
- For app stores and home screen

**How to create icons:**
1. Use your company logo
2. Resize to 192x192 and 512x512
3. Save as PNG format
4. Place in project root folder

**Free icon generators:**
- https://www.favicon-generator.org/
- https://realfavicongenerator.net/
- https://www.canva.com/

### Step 2: Register Service Worker

Add this HTML to your Streamlit app (in the CSS section or as a separate HTML injection):

```html
<script>
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js')
            .then(function(registration) {
                console.log('Service Worker registered with scope:', registration.scope);
            })
            .catch(function(error) {
                console.log('Service Worker registration failed:', error);
            });
    });
}
</script>
```

Add this to your `lynx app.py` after the CSS section:

```python
st.markdown("""
<script>
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js')
            .then(function(registration) {
                console.log('Service Worker registered');
            })
            .catch(function(error) {
                console.log('Service Worker registration failed:', error);
            });
    });
}
</script>
""", unsafe_allow_html=True)
```

### Step 3: Test PWA

**On Desktop (Chrome/Edge):**
1. Open app in browser
2. Click install icon in address bar
3. Install app
4. Test offline functionality

**On Mobile (iOS Safari):**
1. Open app in Safari
2. Tap Share button
3. Select "Add to Home Screen"
4. Follow prompts
5. Test offline

**On Mobile (Android Chrome):**
1. Open app in Chrome
2. Tap menu (three dots)
3. Select "Install App" or "Add to Home Screen"
4. Follow prompts
5. Test offline

### Step 4: Serve Files Correctly

Make sure your web server serves:
- `manifest.json` with `Content-Type: application/manifest+json`
- `sw.js` with `Content-Type: application/javascript`
- Icons with `Content-Type: image/png`

**For Streamlit:**
- Place files in project root
- Streamlit serves static files automatically
- No additional configuration needed

## PWA Features Available

✅ **Installable** - Can be installed on home screen
✅ **Offline Support** - Works without internet (cached pages)
✅ **Mobile Responsive** - Optimized for phones and tablets
✅ **App-like Experience** - Full screen, no browser UI
✅ **Fast Loading** - Cached resources load instantly
✅ **Push Notifications** - Ready for future implementation

## Limitations

⚠️ **Streamlit Limitations:**
- PWA features limited by Streamlit architecture
- Full offline mode may not work perfectly
- Some Streamlit features require internet
- Service worker may not cache dynamic content

⚠️ **Browser Support:**
- Best on Chrome/Edge (desktop & Android)
- Good on Safari (iOS)
- Limited on Firefox

## Next Steps (Optional)

1. **Add Push Notifications** - Requires additional setup
2. **Add Background Sync** - Sync data when online
3. **Add App Badges** - Show notification count
4. **Add Share Target** - Allow sharing to app
5. **Add Custom Splash Screen** - Branded loading screen

## Support

If you encounter issues:
1. Check browser console for errors
2. Verify files are in correct location
3. Ensure file permissions are correct
4. Test in different browsers
5. Check network tab for service worker status

## Summary

Your Lynx Fiber ERP is now PWA-ready! Staff can:
- Install app on their phones
- Use it offline (limited)
- Have app-like experience
- Access from home screen

No additional development needed - just add the icons and test!
