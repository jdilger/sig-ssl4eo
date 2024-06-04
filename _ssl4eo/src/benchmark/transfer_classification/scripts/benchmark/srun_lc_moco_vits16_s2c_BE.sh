#!/usr/bin/env bash

# slurm job configuration
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --ntasks-per-node=4
#SBATCH --output=srun_outputs/classification/BE_moco_LC_vits16_100_%j.out
#SBATCH --error=srun_outputs/classification/BE_moco_LC_vits16_100_%j.err
#SBATCH --time=10:00:00
#SBATCH --job-name=BE_LC_moco
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=10
#SBATCH --partition=booster

master_node=${SLURM_NODELIST:0:9}${SLURM_NODELIST:10:4}
dist_url="tcp://"
dist_url+=$master_node
dist_url+=:40000


# load required modules
module load Stages/2022
module load GCCcore/.11.2.0
module load Python

# activate virtual environment
source /p/project/hai_dm4eo/wang_yi/env2/bin/activate

# define available gpus
export CUDA_VISIBLE_DEVICES=0,1,2,3

# run script as slurm job
srun python -u linear_BE_moco_v3.py \
--data /p/scratch/hai_ssl4eo/data/bigearthnet/BigEarthNet_LMDB_uint8 \
--bands all \
--checkpoints_dir /p/project/hai_ssl4eo/wang_yi/ssl4eo-s12-dataset/src/benchmark/fullset_temp/checkpoints/moco_lc/BE_vits16_100 \
--arch vit_small \
--train_frac 1.0 \
--batch_size 64 \
--lr 0.1 \
--cos \
--epochs 100 \
--num_workers 10 \
--seed 42 \
--dist_url $dist_url \
--linear \
--pretrained /p/project/hai_ssl4eo/wang_yi/ssl4eo-s12-dataset/src/benchmark/fullset_temp/checkpoints/moco/B13_vits16_224/checkpoint_0099.pth.tar \
#--resume /p/project/hai_ssl4eo/wang_yi/ssl4eo-s12-dataset/src/benchmark/fullset_temp/checkpoints/moco_lc/BE_rn50_10_r112/checkpoint_0009.pth.tar
