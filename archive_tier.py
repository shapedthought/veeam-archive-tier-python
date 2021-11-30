from typing import List
from rich.console import Console
from rich.table import Table
from rich.text import Text
import plotext as plt
import yaml
from yaml.loader import SafeLoader

console = Console()
text = Text()

# get all the fields
def archive_cal(data: List) -> None:
    # variables
    source_cap = data['source_cap']
    change_rate = data['change_rate']
    growth = data['growth']
    scope = data['scope']
    comp = data['comp']
    months = data['months']
    tier_after = data['tier_after']
    read_fee = data['read_fee']
    retrieve_fee = data['retrieve_fee']
    storage_fee = data['storage_fee']
    write_fee = data['write_fee']
    block_size = data['block_size']
    compute_cost = data['compute_cost']
    throughput = data['throughput']
    min_retention = data['min_retention']
    change_rate_modifier = data['change_rate_modifier']
    # Each Archive Tier GFS retention point contains 512 capacity tier blocks. 
    # Existing Archive Tier blocks will only be re-used if all 512 contiguous blocks are in the latest RP
    gfs_increase = 2 # set figure, further research needed

    # End of variables 

    if months < tier_after:
        text.append("No data tiered! Check tier_after Parameter", style="red")
        console.print(text)
        return

    # first calculate the capacities per-month
    growth_prorate = growth / 12
    scope_months = scope * 12
    source_compress = source_cap * (1 - comp)

    # per tb metrics
    block_compress = block_size * (1 - comp)
    read_per_tb = (1024**2) / block_compress
    write_per_tb = read_per_tb / 512
    per_tb_compute = (((1024**2) / throughput) / 60**2) * compute_cost

    # per tb costs
    cost_per_tb = storage_fee * 1024 # storage cost
    read_cost_tb = (read_per_tb / 1000) * read_fee 
    retrieve_cost_tb = (read_per_tb / 1000) * retrieve_fee
    write_cost_tb = (write_per_tb / 1000) * write_fee

    # Tracking lists
    month_cap_full = []
    month_cap_inc = []
    process_cap_full = []
    process_cap_inc = []
    month_cap_full_cu = []
    month_cap_inc_cu = []
    tier_month = 1
    full_delete_list = []
    inc_delete_list = []

    # calculate the quantity of months in archive tier
    at_months = (months - tier_after)
    add_charge_months = min_retention - at_months if at_months < min_retention else 0

    # Loop through each month to prorate growth
    for i in range(scope_months):
        if i >= tier_after + 1:
            # does a check in case the growth is set to zero
            current_cap = source_compress if growth_prorate == 0 else source_compress + ( source_compress * (growth_prorate * tier_month))
            current_cap_inc = (current_cap * (change_rate * change_rate_modifier)) * gfs_increase
            tier_month += 1

        if i == tier_after + 1:
            # On first run add the full capacity to all lists
            month_cap_full_cu.append(current_cap)
            month_cap_inc_cu.append(current_cap)
            process_cap_full.append(current_cap)
            process_cap_inc.append(current_cap)
            full_delete_list.append(0)
            inc_delete_list.append(0)
        elif i > tier_after + 1:
            # After that point we start the usual offloads
            month_cap_full.append(current_cap)
            month_cap_inc.append(current_cap_inc)
            process_cap_full.append(current_cap)
            process_cap_inc.append(current_cap_inc)
            # Adjust the retention to the min retention
            at_months = (months - tier_after)
            charge_months = 0
                    
            # Calculate the normal deletions
            full_delete = 0
            inc_delete = 0
            if len(month_cap_full) > at_months:
                full_delete = month_cap_full.pop(0)
                inc_delete = month_cap_inc.pop(0)
            full_delete_list.append(full_delete)
            inc_delete_list.append(inc_delete)
            month_cap_full_cu.append(current_cap + month_cap_full_cu[-1] - full_delete)
            month_cap_inc_cu.append(current_cap_inc + month_cap_inc_cu[-1] - inc_delete)
        else:
            # This adds a zero not at the tiering point
            month_cap_full_cu.append(0)
            month_cap_inc_cu.append(0)
            process_cap_full.append(0)
            process_cap_inc.append(0)
            full_delete_list.append(0)
            inc_delete_list.append(0)

    # Costs section
    # Storage Costs
    full_cost_list = [x * cost_per_tb for x in month_cap_full_cu]
    inc_cost_list = [x * cost_per_tb for x in month_cap_inc_cu]

    # Processing Costs
    process_cost_tb = per_tb_compute + read_cost_tb + write_cost_tb + retrieve_cost_tb
    full_process_cost= [x * process_cost_tb for x in process_cap_full]
    inc_process_cost = [x * process_cost_tb for x in process_cap_inc]

    # Early delete Costs
    ed_cost_full = []
    ed_cost_inc = []
    if add_charge_months > 0:
        ed_cost_full = [x * (cost_per_tb * add_charge_months ) for x in full_delete_list]
        ed_cost_inc = [x * (cost_per_tb * add_charge_months) for x in inc_delete_list]
    else:
        ed_cost_full = [0] * len(full_cost_list)
        ed_cost_inc = [0] * len(inc_delete_list)

    # Total costs - this is why I love Python
    total_cost_full = [a + b + c for a, b, c in zip(full_cost_list, full_process_cost, ed_cost_full)]
    total_cost_inc = [a + b + c for a, b, c in zip(inc_cost_list, inc_process_cost, ed_cost_inc)]

    print("")
    table = Table(title="Calculation Results")
    table.add_column("Area", justify="centre", style="white", no_wrap=True)
    table.add_column("Standalone Full", justify="centre", style="white", no_wrap=True)
    table.add_column("Incremental", justify="centre", style="white", no_wrap=True)

    table.add_row("Max Stored Capacity", str(round(month_cap_full_cu[-1],2)), str(round(month_cap_inc_cu[-1],2)))
    table.add_row("Storage Costs", str(round(sum(full_cost_list),2)), str(round(sum(inc_cost_list), 2)))
    table.add_row("Processing Costs", str(round(sum(full_process_cost),2)), str(round(sum(inc_process_cost),2)))
    table.add_row("Early Delete Costs",str(round(sum(ed_cost_full),2)), str(round(sum(ed_cost_inc),2)))
    table.add_row("Total Costs", str(round(sum(total_cost_full),2)), str(round(sum(total_cost_inc),2)))

    console.print(table)
    print("")

    plt.clp()
    plt.plot_size(100, 50)
    plt.plot(total_cost_inc, label="Inc Costs", color="black")
    plt.plot(total_cost_full, label="Full Costs", color="bright-green")
    plt.title("Costs Over Time")
    plt.show()

if __name__ == "__main__":
    with open("inputs.yaml") as f:
        data = yaml.load(f, Loader=SafeLoader)
    archive_cal(data)