import sys
import os
import json
import gzip
import re
import copy
import xml.etree.ElementTree as ET
import urllib.request


# ============================================================
# PATHS
# ============================================================

SVD_DIR = os.path.expanduser("~/digital-twin-project/svd")
CMSIS_DIR = os.path.join(SVD_DIR, "cmsis-svd-data", "data")


# ============================================================
# SVD FILE SEARCH
# ============================================================

def find_svd(device):
    print()
    print("Searching CMSIS-SVD database...")
    print(f"Requested device: {device}")

    target = device.lower() + ".svd"

    if not os.path.exists(CMSIS_DIR):
        print()
        print("ERROR: CMSIS-SVD database not found:")
        print(CMSIS_DIR)
        return None

    for root, dirs, files in os.walk(CMSIS_DIR):
        for filename in files:
            if filename.lower() == target:
                path = os.path.join(root, filename)

                print()
                print("SVD found:")
                print(path)

                return path

    return None


# ============================================================
# DOWNLOAD FALLBACK
# ============================================================

def download_svd(url, filename):
    os.makedirs(SVD_DIR, exist_ok=True)

    output_path = os.path.join(SVD_DIR, filename)

    print()
    print("Downloading SVD from:")
    print(url)
    print()

    urllib.request.urlretrieve(url, output_path)

    print("SVD downloaded successfully.")
    print(f"Saved to: {output_path}")

    return output_path


# ============================================================
# XML LOADING
# ============================================================

def load_xml(svd_path):

    if svd_path.endswith(".gz"):

        with gzip.open(svd_path, "rb") as file:
            tree = ET.parse(file)

    else:

        tree = ET.parse(svd_path)

    return tree.getroot()


# ============================================================
# INTEGER PARSER
# ============================================================

def parse_integer(value):

    if value is None:
        return None

    value = value.strip()

    if value == "":
        return None

    try:
        return int(value, 0)

    except ValueError:
        return None


# ============================================================
# FIELD BIT INFORMATION
# ============================================================

def get_field_bits(field):

    # Format 1:
    # <bitOffset>0</bitOffset>
    # <bitWidth>4</bitWidth>

    bit_offset = field.findtext("bitOffset")
    bit_width = field.findtext("bitWidth")

    if bit_offset is not None and bit_width is not None:

        return (
            parse_integer(bit_offset),
            parse_integer(bit_width)
        )


    # Format 2:
    # <lsb>0</lsb>
    # <msb>3</msb>

    lsb = field.findtext("lsb")
    msb = field.findtext("msb")

    if lsb is not None and msb is not None:

        lsb_value = parse_integer(lsb)
        msb_value = parse_integer(msb)

        if lsb_value is not None and msb_value is not None:

            return (
                lsb_value,
                msb_value - lsb_value + 1
            )


    # Format 3:
    # <bitRange>[3:0]</bitRange>

    bit_range = field.findtext("bitRange")

    if bit_range is not None:

        match = re.match(
            r"\[(\d+):(\d+)\]",
            bit_range.strip()
        )

        if match:

            msb_value = int(match.group(1))
            lsb_value = int(match.group(2))

            return (
                lsb_value,
                msb_value - lsb_value + 1
            )

    return None, None


# ============================================================
# FIELD PARSER
# ============================================================

def parse_field(field):

    bit_offset, bit_width = get_field_bits(field)

    return {

        "name":
            field.findtext("name", ""),

        "description":
            field.findtext("description", ""),

        "bit_offset":
            bit_offset,

        "bit_width":
            bit_width,

        "access":
            field.findtext("access", ""),

        "reset_value":
            field.findtext("resetValue", ""),

        "derived_from":
            field.get("derivedFrom")
    }


# ============================================================
# DIMENSION PARSER
# ============================================================

def parse_dimension(element):

    dim = parse_integer(
        element.findtext("dim")
    )

    dim_increment = parse_integer(
        element.findtext("dimIncrement")
    )

    dim_index = element.findtext(
        "dimIndex"
    )

    if (
        dim is None
        and dim_increment is None
        and dim_index is None
    ):
        return None

    return {

        "dim":
            dim,

        "dim_increment":
            dim_increment,

        "dim_index":
            dim_index
    }


# ============================================================
# REGISTER PARSER
# ============================================================

def parse_register(register):

    address_offset = parse_integer(
        register.findtext("addressOffset")
    )

    size = parse_integer(
        register.findtext("size")
    )


    # ----------------------------
    # Fields
    # ----------------------------

    fields = []

    fields_element = register.find("fields")

    if fields_element is not None:

        for field in fields_element.findall("field"):

            fields.append(
                parse_field(field)
            )


    # ----------------------------
    # Dimension
    # ----------------------------

    dimension = parse_dimension(
        register
    )


    return {

        "name":
            register.findtext("name", ""),

        "display_name":
            register.findtext("displayName", ""),

        "description":
            register.findtext("description", ""),

        "derived_from":
            register.get("derivedFrom"),

        "address_offset":
            address_offset,

        "size":
            size,

        "access":
            register.findtext("access", ""),

        "reset_value":
            register.findtext("resetValue", ""),

        "reset_mask":
            register.findtext("resetMask", ""),

        "dimension":
            dimension,

        "fields":
            fields
    }


# ============================================================
# CLUSTER PARSER
# ============================================================

def parse_cluster(cluster):

    address_offset = parse_integer(
        cluster.findtext("addressOffset")
    )

    dimension = parse_dimension(
        cluster
    )


    registers = []

    # IMPORTANT:
    #
    # Nordic SVD files place registers
    # directly inside the cluster.
    #
    # <cluster>
    #     ...
    #     <register>
    #         ...
    #     </register>
    # </cluster>

    for register in cluster.findall("register"):

        registers.append(
            parse_register(register)
        )


    # Some SVD files may contain
    # another <registers> container.
    #
    # Support that format too.

    registers_element = cluster.find("registers")

    if registers_element is not None:

        for register in registers_element.findall("register"):

            registers.append(
                parse_register(register)
            )


    # Nested clusters

    nested_clusters = []

    for child_cluster in cluster.findall("cluster"):

        nested_clusters.append(
            parse_cluster(child_cluster)
        )


    return {

        "name":
            cluster.findtext("name", ""),

        "description":
            cluster.findtext("description", ""),

        "derived_from":
            cluster.get("derivedFrom"),

        "address_offset":
            address_offset,

        "dimension":
            dimension,

        "registers":
            registers,

        "clusters":
            nested_clusters
    }


# ============================================================
# PERIPHERAL PARSER
# ============================================================

def parse_peripheral(peripheral):

    base_address = parse_integer(
        peripheral.findtext("baseAddress")
    )


    registers = []

    clusters = []


    registers_element = peripheral.find(
        "registers"
    )


    if registers_element is not None:


        # ----------------------------
        # Direct registers
        # ----------------------------

        for register in registers_element.findall(
            "register"
        ):

            parsed_register = parse_register(
                register
            )

            offset = parsed_register[
                "address_offset"
            ]


            if (
                base_address is not None
                and offset is not None
            ):

                parsed_register["address"] = (
                    base_address + offset
                )

            else:

                parsed_register["address"] = None


            registers.append(
                parsed_register
            )


        # ----------------------------
        # Clusters
        # ----------------------------

        for cluster in registers_element.findall(
            "cluster"
        ):

            parsed_cluster = parse_cluster(
                cluster
            )

            clusters.append(
                parsed_cluster
            )


    # ----------------------------
    # Address block
    # ----------------------------

    address_block = peripheral.find(
        "addressBlock"
    )

    address_block_data = {}


    if address_block is not None:

        address_block_data = {

            "offset":
                parse_integer(
                    address_block.findtext("offset")
                ),

            "size":
                parse_integer(
                    address_block.findtext("size")
                ),

            "usage":
                address_block.findtext(
                    "usage", ""
                )
        }


    # ----------------------------
    # Interrupts
    # ----------------------------

    interrupts = []


    for interrupt in peripheral.findall(
        "interrupt"
    ):

        interrupts.append({

            "name":
                interrupt.findtext(
                    "name", ""
                ),

            "description":
                interrupt.findtext(
                    "description", ""
                ),

            "value":
                parse_integer(
                    interrupt.findtext("value")
                )
        })


    return {

        "name":
            peripheral.findtext("name", ""),

        "description":
            peripheral.findtext(
                "description", ""
            ),

        "group_name":
            peripheral.findtext(
                "groupName", ""
            ),

        "derived_from":
            peripheral.get("derivedFrom"),

        "base_address":
            base_address,

        "address_block":
            address_block_data,

        "interrupts":
            interrupts,

        "registers":
            registers,

        "clusters":
            clusters
    }


# ============================================================
# PERIPHERAL INHERITANCE
# ============================================================

def resolve_peripheral_inheritance(
    peripherals
):

    print()
    print("Resolving peripheral inheritance...")


    peripheral_map = {

        peripheral["name"]:
            peripheral

        for peripheral in peripherals

    }


    resolved_count = 0


    for peripheral in peripherals:

        parent_name = peripheral[
            "derived_from"
        ]


        if not parent_name:
            continue


        parent = peripheral_map.get(
            parent_name
        )


        if parent is None:

            print(
                f"WARNING: Parent peripheral "
                f"'{parent_name}' not found "
                f"for '{peripheral['name']}'"
            )

            continue


        # Copy parent registers
        # only if child has none.

        if not peripheral["registers"]:

            peripheral["registers"] = copy.deepcopy(
                parent["registers"]
            )


            # Recalculate absolute addresses
            # using child's base address.

            base_address = peripheral[
                "base_address"
            ]


            for register in peripheral[
                "registers"
            ]:

                offset = register[
                    "address_offset"
                ]


                if (
                    base_address is not None
                    and offset is not None
                ):

                    register["address"] = (
                        base_address + offset
                    )

                else:

                    register["address"] = None


        # Copy clusters only if child
        # does not define its own clusters.

        if not peripheral["clusters"]:

            peripheral["clusters"] = copy.deepcopy(
                parent["clusters"]
            )


        resolved_count += 1


        print(
            f"  {peripheral['name']} "
            f"<- {parent_name}"
        )


    print(
        f"Peripheral inheritance resolved: "
        f"{resolved_count}"
    )


# ============================================================
# REGISTER INHERITANCE
# ============================================================

def resolve_register_inheritance(
    peripheral
):

    register_map = {

        register["name"]:
            register

        for register in peripheral[
            "registers"
        ]

    }


    resolved_count = 0


    for register in peripheral[
        "registers"
    ]:

        parent_name = register[
            "derived_from"
        ]


        if not parent_name:
            continue


        # CMSIS-SVD register derivedFrom
        # may be written using the register
        # name directly or with a peripheral
        # prefix.

        parent_name_clean = parent_name.split(
            "."
        )[-1]


        parent = register_map.get(
            parent_name_clean
        )


        if parent is None:
            continue


        original_name = register[
            "name"
        ]

        original_offset = register[
            "address_offset"
        ]


        inherited = copy.deepcopy(
            parent
        )


        inherited["name"] = original_name

        inherited["derived_from"] = (
            parent_name
        )


        # Child-specific values override
        # inherited values.

        if original_offset is not None:

            inherited[
                "address_offset"
            ] = original_offset


        for key in (
            "display_name",
            "description",
            "size",
            "access",
            "reset_value",
            "reset_mask",
            "dimension",
            "fields"
        ):

            if register.get(key) not in (
                None,
                "",
                []
            ):

                inherited[key] = register[
                    key
                ]


        register.clear()

        register.update(
            inherited
        )


        base_address = peripheral[
            "base_address"
        ]

        offset = register[
            "address_offset"
        ]


        if (
            base_address is not None
            and offset is not None
        ):

            register["address"] = (
                base_address + offset
            )


        resolved_count += 1


    return resolved_count


# ============================================================
# CLUSTER REGISTER ADDRESS RESOLUTION
# ============================================================

def resolve_cluster_addresses(
    clusters,
    base_address,
    parent_offset=0
):

    for cluster in clusters:

        cluster_offset = cluster[
            "address_offset"
        ]


        if cluster_offset is None:

            cluster_offset = 0


        current_offset = (
            parent_offset
            + cluster_offset
        )


        # Registers directly inside cluster

        for register in cluster[
            "registers"
        ]:

            register_offset = register[
                "address_offset"
            ]


            if register_offset is None:
                continue


            register["address"] = (
                base_address
                + current_offset
                + register_offset
            )


        # Nested clusters

        resolve_cluster_addresses(

            cluster["clusters"],

            base_address,

            current_offset
        )


# ============================================================
# COMPLETE INHERITANCE RESOLUTION
# ============================================================

def resolve_inheritance(device):

    peripherals = device[
        "peripherals"
    ]


    # Peripheral inheritance first

    resolve_peripheral_inheritance(
        peripherals
    )


    # Register inheritance

    register_inheritance_count = 0


    for peripheral in peripherals:

        register_inheritance_count += (
            resolve_register_inheritance(
                peripheral
            )
        )


    # Cluster addresses

    for peripheral in peripherals:

        base_address = peripheral[
            "base_address"
        ]


        if base_address is not None:

            resolve_cluster_addresses(

                peripheral["clusters"],

                base_address
            )


    print(
        f"Register inheritance resolved: "
        f"{register_inheritance_count}"
    )


# ============================================================
# SVD PARSER
# ============================================================

def parse_svd(svd_path):

    print()
    print("Parsing SVD...")
    print(f"File: {svd_path}")


    root = load_xml(
        svd_path
    )


    device = {

        "name":
            root.findtext(
                "name", ""
            ),

        "description":
            root.findtext(
                "description", ""
            ),

        "version":
            root.findtext(
                "version", ""
            ),

        "address_unit_bits":
            parse_integer(
                root.findtext(
                    "addressUnitBits"
                )
            ),

        "width":
            parse_integer(
                root.findtext(
                    "width"
                )
            ),

        "cpu":
            {},

        "peripherals":
            []
    }


    # ----------------------------
    # CPU
    # ----------------------------

    cpu = root.find(
        "cpu"
    )


    if cpu is not None:

        device["cpu"] = {

            "name":
                cpu.findtext(
                    "name", ""
                ),

            "revision":
                cpu.findtext(
                    "revision", ""
                ),

            "endian":
                cpu.findtext(
                    "endian", ""
                ),

            "mpu_present":
                cpu.findtext(
                    "mpuPresent", ""
                ),

            "fpu_present":
                cpu.findtext(
                    "fpuPresent", ""
                ),

            "nvic_prio_bits":
                parse_integer(
                    cpu.findtext(
                        "nvicPrioBits"
                    )
                )
        }


    # ----------------------------
    # Peripherals
    # ----------------------------

    peripherals = root.find(
        "peripherals"
    )


    if peripherals is None:

        print()
        print(
            "WARNING: No peripherals found."
        )

        return device


    for peripheral in peripherals.findall(
        "peripheral"
    ):

        device["peripherals"].append(
            parse_peripheral(
                peripheral
            )
        )


    # ----------------------------
    # Resolve inheritance
    # ----------------------------

    resolve_inheritance(
        device
    )


    return device


# ============================================================
# SAVE JSON
# ============================================================

def save_json(device):

    filename = (
        device["name"]
        + "_hardware.json"
    )


    output_path = os.path.join(
        SVD_DIR,
        filename
    )


    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            device,
            file,
            indent=4
        )


    return output_path


# ============================================================
# SUMMARY
# ============================================================

def print_summary(device):

    print()
    print(
        "========================================"
    )
    print(
        "       DIGITAL TWIN HARDWARE MODEL"
    )
    print(
        "========================================"
    )


    print()

    print(
        f"Device       : "
        f"{device['name']}"
    )

    print(
        f"Description  : "
        f"{device['description']}"
    )

    print(
        f"Width        : "
        f"{device['width']} bits"
    )

    print(
        f"Address unit : "
        f"{device['address_unit_bits']} bits"
    )


    cpu = device["cpu"]


    if cpu:

        print()
        print("CPU")

        print(
            f"  Name       : "
            f"{cpu['name']}"
        )

        print(
            f"  Revision   : "
            f"{cpu['revision']}"
        )

        print(
            f"  Endian     : "
            f"{cpu['endian']}"
        )


    peripherals = device[
        "peripherals"
    ]


    print()

    print(
        f"Peripherals  : "
        f"{len(peripherals)}"
    )


    register_count = 0
    field_count = 0
    cluster_count = 0
    interrupt_count = 0


    def count_cluster(cluster):

        nonlocal register_count
        nonlocal field_count
        nonlocal cluster_count

        cluster_count += 1

        for register in cluster[
            "registers"
        ]:

            register_count += 1

            field_count += len(
                register["fields"]
            )


        for nested in cluster[
            "clusters"
        ]:

            count_cluster(
                nested
            )


    for peripheral in peripherals:

        register_count += len(
            peripheral["registers"]
        )

        interrupt_count += len(
            peripheral["interrupts"]
        )


        for register in peripheral[
            "registers"
        ]:

            field_count += len(
                register["fields"]
            )


        for cluster in peripheral[
            "clusters"
        ]:

            count_cluster(
                cluster
            )


    print(
        f"Registers    : "
        f"{register_count}"
    )

    print(
        f"Fields       : "
        f"{field_count}"
    )

    print(
        f"Clusters     : "
        f"{cluster_count}"
    )

    print(
        f"Interrupts   : "
        f"{interrupt_count}"
    )


    print()
    print(
        "First 10 peripherals:"
    )


    for peripheral in peripherals[:10]:

        base = peripheral[
            "base_address"
        ]


        base_text = (
            hex(base)
            if base is not None
            else "N/A"
        )


        print(
            f"  "
            f"{peripheral['name']:<12}"
            f" Base: {base_text}"
        )


    if len(peripherals) > 10:

        print(
            f"  ... and "
            f"{len(peripherals) - 10}"
            f" more"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    if len(sys.argv) != 2:

        print()
        print("Usage:")
        print(
            "python3 svd_manager.py <device>"
        )

        print()

        print("Examples:")

        print(
            "python3 svd_manager.py "
            "STM32F407"
        )

        print(
            "python3 svd_manager.py "
            "nRF52840"
        )

        return


    device = sys.argv[1]


    print()

    print(
        f"Requested device: {device}"
    )


    svd_path = find_svd(
        device
    )


    if svd_path is None:

        print()

        print(
            f"No CMSIS-SVD found for: "
            f"{device}"
        )


        renode_database = {

            "STM32F40x":
                "https://dl.antmicro.com/"
                "projects/renode/svd/"
                "STM32F40x.svd.gz"
        }


        if device not in renode_database:

            print()

            print(
                f"No fallback SVD configured "
                f"for: {device}"
            )

            print()

            print(
                "Please use a device available "
                "in the CMSIS-SVD database."
            )

            return


        svd_path = download_svd(

            renode_database[device],

            device + ".svd.gz"
        )


    try:

        hardware_model = parse_svd(
            svd_path
        )

    except Exception as error:

        print()

        print(
            "ERROR while parsing SVD:"
        )

        print(error)

        return


    print_summary(
        hardware_model
    )


    output_path = save_json(
        hardware_model
    )


    print()

    print(
        "JSON hardware model saved:"
    )

    print(
        output_path
    )


    print()

    print(
        "SVD Manager completed successfully."
    )


if __name__ == "__main__":

    main()
