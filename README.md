# Hanna Cloud Integration for Home Assistant

This custom integration allows you to monitor your Hanna Instruments pH/redox/temperature controllers through Home Assistant by connecting to the Hanna Cloud service.

## Features

- **pH Monitoring**: Track pH levels from your Hanna instruments
- **Temperature Monitoring**: Monitor water temperature
- **Redox/ORP Monitoring**: Track oxidation-reduction potential
- **Device Status**: Monitor device connectivity and battery status
- **Tank Information**: Display tank names and device assignments
- **Automatic Authentication**: Handles token refresh automatically
- **Configurable Update Intervals**: Set how often data is fetched (1-60 minutes)

## Installation

### Method 1: Manual Installation

1. Create a new folder in your `custom_components` directory called `hanna_cloud`
2. Copy all the Python files into this folder:
   ```
   custom_components/
   └── hanna_cloud/
       ├── __init__.py
       ├── config_flow.py
       ├── const.py
       ├── sensor.py
       ├── manifest.json
       └── strings.json
   ```

### Method 2: HACS Installation (Future)

Once published to HACS, you can install it directly through the HACS interface.

## Configuration

1. **Add Integration**: Go to Settings → Devices & Services → Add Integration
2. **Search**: Look for "Hanna Cloud" in the integration list
3. **Enter Credentials**: 
   - Email: Your Hanna Cloud login email
   - Password: Your Hanna Cloud password
4. **Complete Setup**: The integration will authenticate and discover your devices

## Configuration Options

After setup, you can configure the following options:

- **Update Interval**: How often to fetch new data (1-60 minutes, default: 5 minutes)

## Supported Devices

This integration supports the following Hanna Instruments device model groups:
- BL12x series
- BL13x series  
- BL13xs series
- HALO series
- photoMeter series
- multiParameter series

## Entities Created

For each device, the integration creates the following entities:

### Sensors
- **pH Sensor**: Displays current pH value
- **Temperature Sensor**: Shows water temperature in Celsius
- **Redox Sensor**: Shows oxidation-reduction potential in millivolts (mV)
- **Status Sensor**: Device connection and operational status

### Device Information
Each device includes:
- Device name and ID
- Model group and version
- Tank name (if configured)
- Battery status
- Last update time

## Usage Examples

### Automations

**pH Alert Automation**:
```yaml
automation:
  - alias: "Pool pH Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.pool_controller_ph
        below: 7.0
        for: "00:05:00"
    action:
      - service: notify.mobile_app
        data:
          message: "Pool pH is too low: {{ states('sensor.pool_controller_ph') }}"
```

**Temperature Monitoring**:
```yaml
automation:
  - alias: "Pool Temperature Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.pool_controller_temperature
        above: 30
    action:
      - service: notify.pushbullet
        data:
          message: "Pool temperature is high: {{ states('sensor.pool_controller_temperature') }}°C"
```

### Dashboard Cards

**Gauge Card for pH**:
```yaml
type: gauge
entity: sensor.pool_controller_ph
min: 6
max: 8
needle: true
severity:
  green: 7.2
  yellow: 7.0
  red: 6.8
```

**History Graph**:
```yaml
type: history-graph
entities:
  - sensor.pool_controller_ph
  - sensor.pool_controller_temperature
  - sensor.pool_controller_redox
hours_to_show: 24
```

## Troubleshooting

### Common Issues

**Authentication Failed**:
- Verify your email and password are correct
- Check that your Hanna Cloud account is active
- Ensure you can log in to the Hanna Cloud website

**No Devices Found**:
- Verify your devices are connected to Hanna Cloud
- Check that devices are online in the Hanna Cloud dashboard
- Ensure devices are in supported model groups

**Connection Timeouts**:
- Check your internet connection
- Verify Home Assistant can reach hannacloud.com
- Try increasing the update interval

### Debug Logging

To enable debug logging, add this to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.hanna_cloud: debug
```

## API Details

The integration uses the Hanna Cloud GraphQL API:
- **Authentication Endpoint**: `https://hannacloud.com/api/auth`
- **GraphQL Endpoint**: `https://hannacloud.com/api/graphql`
- **Authentication**: JWT Bearer tokens with automatic refresh

## Security Notes

- Credentials are stored securely in Home Assistant's configuration
- API tokens are refreshed automatically when they expire
- All communication uses HTTPS encryption

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

- **Issues**: Report bugs and feature requests on GitHub
- **Discussions**: Join the Home Assistant community forums
- **Documentation**: Refer to the Hanna Instruments documentation for device-specific information

## Changelog

### Version 1.0.0
- Initial release
- Support for pH, temperature, and redox sensors
- Device status monitoring
- Configurable update intervals
- Automatic token refresh