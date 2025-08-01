from tqdm import tqdm
train_profiles = range(10)


total_training_steps = len(train_profiles) * total_epochs


        # add tqdm
progress_bar = tqdm(total=total_training_steps, initial=global_steps, desc="Training Progress")
        
        
for epoch in range(total_epochss):
            
    for start_idx in range(0, len(train_profiles), config.data.train_batch_size):
        
        is_last_step = global_steps >= total_training_steps

        progress_bar.update(1)
        global_steps += 1
        if is_last_step:
            progress_bar.close()
