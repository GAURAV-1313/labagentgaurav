import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';

void main() {
  runApp(const AppBlockerApp());
}

class AppBlockerApp extends StatelessWidget {
  const AppBlockerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'App Blocker',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal),
        useMaterial3: true,
      ),
      home: const BlockerHome(),
    );
  }
}

class BlockerHome extends StatefulWidget {
  const BlockerHome({super.key});

  @override
  State<BlockerHome> createState() => _BlockerHomeState();
}

class _BlockerHomeState extends State<BlockerHome> {
  static const _channel = MethodChannel('app_blocker/native');
  final TextEditingController _searchController = TextEditingController();
  final TextEditingController _messageController = TextEditingController();

  bool _usageGranted = false;
  bool _overlayGranted = false;
  bool _loadingApps = false;

  final List<_InstalledApp> _allApps = [];
  final Set<String> _selectedPackages = {};
  String _imagePath = '';

  @override
  void initState() {
    super.initState();
    _refreshPermissions();
    _loadInstalledApps();
    _loadBlockScreenConfig();
  }

  Future<void> _refreshPermissions() async {
    final usage = await _channel.invokeMethod<bool>('isUsageAccessGranted');
    final overlay = await _channel.invokeMethod<bool>('isOverlayGranted');
    if (!mounted) return;
    setState(() {
      _usageGranted = usage ?? false;
      _overlayGranted = overlay ?? false;
    });
  }

  Future<void> _openUsageSettings() async {
    await _channel.invokeMethod('openUsageAccessSettings');
  }

  Future<void> _openOverlaySettings() async {
    await _channel.invokeMethod('openOverlaySettings');
  }

  Future<void> _startService() async {
    await _channel.invokeMethod('startService');
  }

  Future<void> _stopService() async {
    await _channel.invokeMethod('stopService');
  }

  Future<void> _setBlockedApps() async {
    await _channel.invokeMethod('setBlockedApps', {
      'packages': _selectedPackages.toList(),
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    _messageController.dispose();
    super.dispose();
  }

  Future<void> _loadInstalledApps() async {
    setState(() {
      _loadingApps = true;
    });
    final result = await _channel.invokeMethod<List<dynamic>>('getInstalledApps');
    final apps = (result ?? [])
        .whereType<Map>()
        .map(
          (item) => _InstalledApp(
            label: item['label']?.toString() ?? item['package']?.toString() ?? '',
            packageName: item['package']?.toString() ?? '',
          ),
        )
        .where((app) => app.packageName.isNotEmpty)
        .toList();
    apps.sort((a, b) => a.label.toLowerCase().compareTo(b.label.toLowerCase()));
    if (!mounted) return;
    setState(() {
      _allApps
        ..clear()
        ..addAll(apps);
      _loadingApps = false;
    });
  }

  Future<void> _loadBlockScreenConfig() async {
    final result =
        await _channel.invokeMethod<Map<dynamic, dynamic>>('getBlockScreenConfig');
    if (!mounted) return;
    setState(() {
      _messageController.text = result?['message']?.toString() ?? '';
      _imagePath = result?['imagePath']?.toString() ?? '';
    });
  }

  Future<void> _saveBlockScreenConfig() async {
    await _channel.invokeMethod('setBlockScreenConfig', {
      'message': _messageController.text.trim(),
      'imagePath': _imagePath,
    });
  }

  Future<void> _pickImage() async {
    final picker = ImagePicker();
    final picked = await picker.pickImage(source: ImageSource.gallery);
    if (picked == null) return;
    final directory = await getApplicationDocumentsDirectory();
    final targetPath = '${directory.path}/block_image_${DateTime.now().millisecondsSinceEpoch}.jpg';
    final savedFile = await File(picked.path).copy(targetPath);
    if (!mounted) return;
    setState(() {
      _imagePath = savedFile.path;
    });
  }

  void _clearImage() {
    setState(() {
      _imagePath = '';
    });
  }

  @override
  Widget build(BuildContext context) {
    final query = _searchController.text.trim().toLowerCase();
    final visibleApps = query.isEmpty
        ? _allApps
        : _allApps
            .where((app) =>
                app.label.toLowerCase().contains(query) ||
                app.packageName.toLowerCase().contains(query))
            .toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('App Blocker'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            'Permissions',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          _PermissionTile(
            title: 'Usage Access',
            granted: _usageGranted,
            onPressed: _openUsageSettings,
          ),
          _PermissionTile(
            title: 'Overlay Permission',
            granted: _overlayGranted,
            onPressed: _openOverlaySettings,
          ),
          const SizedBox(height: 12),
          OutlinedButton(
            onPressed: _refreshPermissions,
            child: const Text('Refresh permissions'),
          ),
          const SizedBox(height: 24),
          Text(
            'Pick apps to block',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _searchController,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              hintText: 'Search apps',
              prefixIcon: Icon(Icons.search),
            ),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 12),
          ElevatedButton(
            onPressed: _setBlockedApps,
            child: const Text('Save blocked apps'),
          ),
          const SizedBox(height: 12),
          if (_loadingApps)
            const Center(child: CircularProgressIndicator())
          else if (_allApps.isEmpty)
            const Text('No apps found. Try refreshing.'),
          if (!_loadingApps && _allApps.isNotEmpty)
            ...visibleApps.map(
              (app) => CheckboxListTile(
                value: _selectedPackages.contains(app.packageName),
                title: Text(app.label),
                subtitle: Text(app.packageName),
                onChanged: (checked) {
                  setState(() {
                    if (checked == true) {
                      _selectedPackages.add(app.packageName);
                    } else {
                      _selectedPackages.remove(app.packageName);
                    }
                  });
                },
              ),
            ),
          const SizedBox(height: 24),
          Text(
            'Blocker Control',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          ElevatedButton(
            onPressed: _startService,
            child: const Text('Start blocker'),
          ),
          OutlinedButton(
            onPressed: _stopService,
            child: const Text('Stop blocker'),
          ),
          const SizedBox(height: 24),
          Text(
            'Block Screen',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _messageController,
            maxLines: 2,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              labelText: 'Blocked message',
              hintText: 'Nice try. Focus mode says no.',
            ),
          ),
          const SizedBox(height: 12),
          if (_imagePath.isNotEmpty)
            Column(
              children: [
                Image.file(
                  File(_imagePath),
                  height: 180,
                  fit: BoxFit.cover,
                ),
                const SizedBox(height: 8),
                OutlinedButton(
                  onPressed: _clearImage,
                  child: const Text('Remove image'),
                ),
              ],
            )
          else
            const Text('No image selected.'),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: ElevatedButton(
                  onPressed: _pickImage,
                  child: const Text('Pick image'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: OutlinedButton(
                  onPressed: _saveBlockScreenConfig,
                  child: const Text('Save block screen'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _PermissionTile extends StatelessWidget {
  const _PermissionTile({
    required this.title,
    required this.granted,
    required this.onPressed,
  });

  final String title;
  final bool granted;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        title: Text(title),
        subtitle: Text(granted ? 'Granted' : 'Not granted'),
        trailing: TextButton(
          onPressed: onPressed,
          child: const Text('Open'),
        ),
      ),
    );
  }
}

class _InstalledApp {
  const _InstalledApp({
    required this.label,
    required this.packageName,
  });

  final String label;
  final String packageName;
}
