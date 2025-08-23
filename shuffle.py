import pandas as pd


def shuffle_csv(input_file: str, output_file: str):
    """
    Shuffle rows in a CSV file and save to a new file.

    Args:
        input_file (str): Path to the input CSV file.
        output_file (str): Path where the shuffled file will be saved.
    """
    # Load the CSV into a DataFrame
    df = pd.read_csv(input_file)

    # Shuffle the rows
    df_shuffled = df.sample(frac=1).reset_index(drop=True)

    # Save the shuffled DataFrame back to CSV
    df_shuffled.to_csv(output_file, index=False)

    print(f"Shuffled file saved to: {output_file}")


# Example usage
if __name__ == "__main__":
    shuffle_csv(
        "probate_ops/scripts/publiclandscraper/input_sorted.csv",
        "probate_ops/scripts/publiclandscraper/output_shuffled.csv",
    )
