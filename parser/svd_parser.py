import xml.etree.ElementTree as ET
import json

# Path to the SVD file
SVD_FILE = "../hardware/stm32f4/STM32F40x.svd"

# Parse XML
tree = ET.parse(SVD_FILE)
root = tree.getroot()

# Device name
device_name = root.findtext("name")

print(f"Device: {device_name}")

# Final structured hardware description
hardware = {
    "device": device_name,
    "peripherals": {}
}

# Find all peripherals
peripherals = root.find("peripherals")

for peripheral in peripherals.findall("peripheral"):

    name = peripheral.findtext("name")
    base_address = peripheral.findtext("baseAddress")

    if name is None or base_address is None:
        continue

    peripheral_data = {
        "base_address": base_address,
        "derived_from": peripheral.get("derivedFrom"),
        "registers": {}
    }

    # Registers
    registers = peripheral.find("registers")

    if registers is not None:

        for register in registers.findall("register"):

            reg_name = register.findtext("name")
            offset = register.findtext("addressOffset")
            size = register.findtext("size")
            access = register.findtext("access")
            reset_value = register.findtext("resetValue")

            if reg_name is None:
                continue

            register_data = {
                "offset": offset,
                "size": size,
                "access": access,
                "reset_value": reset_value,
                "fields": {}
            }

            # Fields
            fields = register.find("fields")

            if fields is not None:

                for field in fields.findall("field"):

                    field_name = field.findtext("name")
                    bit_offset = field.findtext("bitOffset")
                    bit_width = field.findtext("bitWidth")
                    field_access = field.findtext("access")

                    if field_name is None:
                        continue

                    register_data["fields"][field_name] = {
                        "bit_offset": bit_offset,
                        "bit_width": bit_width,
                        "access": field_access
                    }

            peripheral_data["registers"][reg_name] = register_data

    hardware["peripherals"][name] = peripheral_data


# Save structured hardware model
with open("hardware_model.json", "w") as file:
    json.dump(hardware, file, indent=4)

print("\nHardware model generated successfully.")
print("Output file: hardware_model.json")
