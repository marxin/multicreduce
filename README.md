# multicreduce
creduce wrapper capable for reducing multiple files

Multi creduce is a wrapper that utilizes creduce command to process
a batch reduction process.

Each multi reduction process consists of ReduceOperations and MergeOperations.

## ReduceOperation:
    * corresponds 1:1 to a creduce command
    * is made of an input file and one output file
    * command syntax contains tokens for input (@0) and output (@$)

## MergeOperation:
    * aggregates produces made by either a Reduce of Merge operation
    * contains N input files (decorated by @0, @1, ... in command)

## Algorithm:
    * for each ReduceOperation we create a classic creduce script file
      that is variable in just the reduction. It means all MergeOperations
      that are not affected by the ReduceOperation are not present in the script
    * one global script is created for a first run
    * we execute one-by-one aforementioned script files with a timeout
    * in each round we increase the timeout until all files are reduced

## Example:
    Please see multicreduce.py source file.
